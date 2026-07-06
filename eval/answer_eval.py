"""Answer-quality eval for the DFFRNT RAG agent.

Runs the full RAG pipeline (retrieve -> prompt -> generate) on the sample
queries and scores the *generated answers*, not just retrieval:

  correctness   answer contains the expected facts (grounded must_include checks)
  citation      answer carries at least one [n] marker
  refusal       out-of-KB negatives and tag-isolation probes refuse (no fabrication)
  latency       wall-clock seconds per answered query (mean / median / max)

Tag-scoped cases (sample_queries.TAG_CASES) go through the same retrieval path
the UI uses when the user filters by tags. The pipeline is built in-process so
generation settings can be overridden per run — pass --temps / --top-ps to
compare settings on the same queries. Each answer is a full local-LLM
generation, so one pass takes tens of minutes with a 30B model.

Examples:
  python -m eval.answer_eval                     # one pass at the live config
  python -m eval.answer_eval --temps 0.1,0.7     # compare two temperatures
  python -m eval.answer_eval --limit 3           # quick smoke test
"""

from __future__ import annotations

import argparse
import re
import statistics
import sys
import time
from typing import List, Optional

from dffrnt_assistant.config import load_settings
from dffrnt_assistant.ollama import OllamaClient
from dffrnt_assistant.rag.pipeline import RagPipeline
from dffrnt_assistant.retrieval.retriever import Retriever
from dffrnt_assistant.retrieval.store import VectorStore

from eval.sample_queries import CASES, NEGATIVE_CASES, REFUSAL_PHRASE, TAG_CASES

_CITE = re.compile(r"\[\d+\]")


def contains_any(text: str, options: List[str]) -> bool:
    low = text.lower()
    return any(opt.lower() in low for opt in options)


def must_include_ok(answer: str, groups: List[List[str]]) -> bool:
    return all(contains_any(answer, group) for group in groups)


def has_citation(answer: str) -> bool:
    return bool(_CITE.search(answer))


def is_refusal(answer: str) -> bool:
    return REFUSAL_PHRASE in answer.lower()


def build_pipeline(settings, temperature: float, top_p: float) -> RagPipeline:
    store = VectorStore(
        settings.qdrant_url, settings.collection_name, settings.vector_size, settings.distance
    )
    llm = OllamaClient(
        settings.ollama_url, settings.llm_model, settings.embed_model,
        temperature, settings.llm_timeout,
        settings.embed_query_prefix, settings.embed_document_prefix,
        settings.llm_num_ctx, top_p, settings.llm_top_k,
        settings.llm_repeat_penalty, settings.llm_num_predict,
    )
    retriever = Retriever(store, llm, settings)
    return RagPipeline(retriever, llm, settings)


def _timed_answer(pipeline, case) -> tuple:
    t0 = time.time()
    result = pipeline.answer(case["query"], None, case.get("tags"))
    return result["answer"], time.time() - t0


def run_suite(pipeline, cases, negatives, verbose: bool) -> dict:
    """Generate + score every case. Returns aggregate metrics."""
    correct = scored = cited = citable = 0
    latencies: List[float] = []
    per_task: dict = {}
    info_lines = []

    def track(task, ok):
        if task:
            t = per_task.setdefault(task, [0, 0])
            t[0] += int(ok)
            t[1] += 1

    for case in cases:
        ans, dt = _timed_answer(pipeline, case)
        latencies.append(dt)
        checks = case.get("checks", {})
        cite_ok = has_citation(ans)

        if case.get("expect_refusal"):
            # Correct behaviour is the canonical (uncited) refusal sentence.
            ok = is_refusal(ans)
            scored += 1
            correct += int(ok)
            track(case.get("task"), ok)
            verdict = "PASS " if ok else "FAIL "
            detail = f"refused={'Y' if ok else 'N'} (isolation)"
        elif checks.get("informational"):
            verdict = "INFO "
            note = "refused" if is_refusal(ans) else "answered"
            detail = f"{note}, cite={'Y' if cite_ok else 'N'}"
        else:
            citable += 1
            cited += int(cite_ok)
            scored += 1
            ok = must_include_ok(ans, checks.get("must_include", []))
            correct += int(ok)
            track(case.get("task"), ok)
            verdict = "PASS " if (ok and cite_ok) else "FAIL "
            detail = f"correct={'Y' if ok else 'N'} cite={'Y' if cite_ok else 'N'}"
        if verbose:
            tag_note = f" [tags={','.join(case['tags'])}]" if case.get("tags") else ""
            info_lines.append(f"  [{verdict}] {detail:<30} {case['note']}{tag_note} ({dt:.0f}s)")

    refused = 0
    for neg in negatives:
        ans, dt = _timed_answer(pipeline, neg)
        latencies.append(dt)
        ok = is_refusal(ans)
        refused += int(ok)
        if verbose:
            info_lines.append(
                f"  [{'PASS ' if ok else 'FAIL '}] {'refused=' + ('Y' if ok else 'N'):<30} "
                f"(neg) {neg['note']} ({dt:.0f}s)"
            )

    if verbose:
        print("\n".join(info_lines))

    n_neg = len(negatives)
    return {
        "correctness": (correct, scored),
        "citation": (cited, citable),
        "refusal": (refused, n_neg),
        "quality": (correct + refused, scored + n_neg),
        "per_task": {k: tuple(v) for k, v in sorted(per_task.items())},
        "latency": latencies,
    }


def fmt(metrics: dict) -> str:
    c, cn = metrics["correctness"]
    ci, cin = metrics["citation"]
    r, rn = metrics["refusal"]
    q, qn = metrics["quality"]
    pct = lambda a, b: f"{(100 * a / b):.0f}%" if b else "n/a"
    return (
        f"correctness {c}/{cn} ({pct(c, cn)})  "
        f"citation {ci}/{cin} ({pct(ci, cin)})  "
        f"refusal {r}/{rn} ({pct(r, rn)})  "
        f"=> quality {q}/{qn} ({pct(q, qn)})"
    )


def fmt_latency(latencies: List[float]) -> str:
    if not latencies:
        return "latency: n/a"
    return (
        f"latency/query: mean {statistics.mean(latencies):.1f}s  "
        f"median {statistics.median(latencies):.1f}s  "
        f"max {max(latencies):.1f}s  (n={len(latencies)})"
    )


def parse_floats(arg: Optional[str], default: float) -> List[float]:
    if not arg:
        return [default]
    return [float(x) for x in arg.split(",") if x.strip()]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--temps", help="comma-separated temperatures to compare")
    ap.add_argument("--top-ps", dest="top_ps", help="comma-separated top_p values")
    ap.add_argument("--limit", type=int, help="only the first N answerable cases (smoke test)")
    ap.add_argument("--no-negatives", action="store_true", help="skip refusal controls")
    ap.add_argument("--no-tags", action="store_true", help="skip tag-scoped cases")
    args = ap.parse_args()

    settings = load_settings()
    temps = parse_floats(args.temps, settings.llm_temperature)
    top_ps = parse_floats(args.top_ps, settings.llm_top_p)
    cases = list(CASES) + ([] if args.no_tags else list(TAG_CASES))
    if args.limit:
        cases = cases[: args.limit]
    negatives = [] if args.no_negatives else NEGATIVE_CASES
    grid = [(t, p) for t in temps for p in top_ps]
    verbose = len(grid) == 1

    print(f"model={settings.llm_model}  top_k={settings.top_k}  "
          f"score_margin={settings.score_margin}  num_ctx={settings.llm_num_ctx}")
    print(f"cases={len(cases)} answerable/scoped + {len(negatives)} negative   "
          f"grid={len(grid)} setting(s)\n")

    rows = []
    for temp, top_p in grid:
        if verbose:
            print(f"--- temperature={temp}  top_p={top_p} ---")
        t0 = time.time()
        pipeline = build_pipeline(settings, temp, top_p)
        metrics = run_suite(pipeline, cases, negatives, verbose)
        dt = time.time() - t0
        line = f"temp={temp:<4} top_p={top_p:<4}  {fmt(metrics)}  ({dt:.0f}s)"
        rows.append(line)
        if verbose:
            print()
            for task, (ok, n) in metrics["per_task"].items():
                print(f"  {task:<15} {ok}/{n}")
            print("  " + fmt_latency(metrics["latency"]))
        print(("\n" if verbose else "") + line + ("\n" if verbose else ""))
        sys.stdout.flush()

    if len(grid) > 1:
        print("\n=== Comparison ===")
        for line in rows:
            print(line)


if __name__ == "__main__":
    main()

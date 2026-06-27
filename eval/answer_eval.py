"""Answer-quality eval for the DFFRNT RAG agent.

Runs the full RAG pipeline (retrieve -> prompt -> generate) on the sample
queries and scores the *generated answers*, not just retrieval:

  correctness   answer contains the expected facts (grounded must_include checks)
  citation      answer carries at least one [n] marker
  refusal       on out-of-KB negative controls, the answer refuses (no fabrication)

The pipeline is built in-process so generation settings can be overridden per
run — pass --temps / --top-ps to compare settings on the same queries and pick
temperature/top_p with evidence. Each answer is a full local-LLM generation, so
a single pass over all queries takes a few minutes; a grid multiplies that.

Examples:
  python -m eval.answer_eval                     # one pass at the live config
  python -m eval.answer_eval --temps 0.1,0.7     # compare two temperatures
  python -m eval.answer_eval --limit 3           # quick smoke test
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from typing import List, Optional

from dffrnt_assistant.config import load_settings
from dffrnt_assistant.ollama import OllamaClient
from dffrnt_assistant.rag.pipeline import RagPipeline
from dffrnt_assistant.retrieval.retriever import Retriever
from dffrnt_assistant.retrieval.store import VectorStore

from eval.sample_queries import CASES, NEGATIVE_CASES, REFUSAL_PHRASE

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


def run_suite(pipeline, cases, negatives, verbose: bool) -> dict:
    """Generate + score every case. Returns aggregate metrics."""
    correct = scored = cited = answerable = 0
    info_lines = []

    for case in cases:
        ans = pipeline.answer(case["query"])["answer"]
        checks = case.get("checks", {})
        cite_ok = has_citation(ans)
        answerable += 1
        cited += int(cite_ok)

        if checks.get("informational"):
            verdict = "INFO "
            note = "refused" if is_refusal(ans) else "answered"
            detail = f"{note}, cite={'Y' if cite_ok else 'N'}"
        else:
            scored += 1
            ok = must_include_ok(ans, checks.get("must_include", []))
            correct += int(ok)
            verdict = "PASS " if (ok and cite_ok) else "FAIL "
            detail = f"correct={'Y' if ok else 'N'} cite={'Y' if cite_ok else 'N'}"
        if verbose:
            info_lines.append(f"  [{verdict}] {detail:<28} {case['note']}")

    refused = 0
    for neg in negatives:
        ans = pipeline.answer(neg["query"])["answer"]
        ok = is_refusal(ans)
        refused += int(ok)
        if verbose:
            info_lines.append(
                f"  [{'PASS ' if ok else 'FAIL '}] {'refused=' + ('Y' if ok else 'N'):<28} "
                f"(neg) {neg['note']}"
            )

    if verbose:
        print("\n".join(info_lines))

    n_neg = len(negatives)
    passes = correct + refused                 # answerable-correct + negatives-refused
    denom = scored + n_neg
    return {
        "correctness": (correct, scored),
        "citation": (cited, answerable),
        "refusal": (refused, n_neg),
        "quality": (passes, denom),
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
    args = ap.parse_args()

    settings = load_settings()
    temps = parse_floats(args.temps, settings.llm_temperature)
    top_ps = parse_floats(args.top_ps, settings.llm_top_p)
    cases = CASES[: args.limit] if args.limit else CASES
    negatives = [] if args.no_negatives else NEGATIVE_CASES
    grid = [(t, p) for t in temps for p in top_ps]
    verbose = len(grid) == 1

    print(f"model={settings.llm_model}  top_k={settings.top_k}  "
          f"score_margin={settings.score_margin}  num_ctx={settings.llm_num_ctx}")
    print(f"cases={len(cases)} answerable + {len(negatives)} negative   "
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
        print(("\n" if verbose else "") + line + ("\n" if verbose else ""))
        sys.stdout.flush()

    if len(grid) > 1:
        print("\n=== Comparison ===")
        for line in rows:
            print(line)


if __name__ == "__main__":
    main()

"""Run a before/after benchmark for chunking changes.

This script compares two ingestion configurations on the same eval corpus:
  - baseline: chunk_floor=0
  - candidate: chunk_floor=128 (or another value you pass)

For each run it:
  1. ingests eval/corpus into its own Qdrant collection
  2. measures retrieval quality (P@1, recall, avg kept chunks)
  3. measures end-to-end answer quality (correctness, citations, refusals)

It keeps all other settings fixed so the only variable is chunking.

Examples:
  .\\.venv\\Scripts\\python.exe -m eval.run_chunk_benchmark
  .\\.venv\\Scripts\\python.exe -m eval.run_chunk_benchmark --candidate-floor 160
"""

from __future__ import annotations

import argparse
import statistics
import time
from dataclasses import replace
from pathlib import Path
import uuid
from typing import Dict, List

from dffrnt_assistant.config import Settings, load_settings
from dffrnt_assistant.ingest.chunker import chunk_file
from dffrnt_assistant.ingest.loaders import load_file
from dffrnt_assistant.ingest.pipeline import build_payload
from dffrnt_assistant.ollama import OllamaClient
from dffrnt_assistant.rag.pipeline import RagPipeline
from dffrnt_assistant.retrieval.retriever import Retriever
from dffrnt_assistant.retrieval.store import VectorStore

from eval.ingest_corpus import CORPUS_DIR, UPLOADS
from eval.sample_queries import CASES, NEGATIVE_CASES, REFUSAL_PHRASE, TAG_CASES


def _contains_any(text: str, options: List[str]) -> bool:
    low = text.lower()
    return any(opt.lower() in low for opt in options)


def _must_include_ok(answer: str, groups: List[List[str]]) -> bool:
    return all(_contains_any(answer, group) for group in groups)


def _has_citation(answer: str) -> bool:
    return "[" in answer and "]" in answer


def _is_refusal(answer: str) -> bool:
    return REFUSAL_PHRASE in answer.lower()


def _build_settings(base: Settings, collection_name: str, chunk_floor: int) -> Settings:
    return replace(base, collection_name=collection_name, chunk_floor=chunk_floor)


def _build_embedder(settings: Settings, temperature: float | None = None, top_p: float | None = None) -> OllamaClient:
    return OllamaClient(
        settings.ollama_url,
        settings.llm_model,
        settings.embed_model,
        settings.llm_temperature if temperature is None else temperature,
        settings.llm_timeout,
        settings.embed_query_prefix,
        settings.embed_document_prefix,
        settings.llm_num_ctx,
        settings.llm_top_p if top_p is None else top_p,
        settings.llm_top_k,
        settings.llm_repeat_penalty,
        settings.llm_num_predict,
    )


def _ingest_corpus(settings: Settings, collection_name: str, chunk_floor: int) -> VectorStore:
    store = VectorStore(settings.qdrant_url, collection_name, settings.vector_size, settings.distance)
    store.recreate_collection()
    embedder = _build_embedder(settings)
    total_chunks = 0
    for filename, (_, description) in UPLOADS.items():
        path = CORPUS_DIR / filename
        document = load_file(str(path))
        chunks = chunk_file(
            document,
            strategy=settings.chunk_strategy,
            chunk_size=settings.chunk_size,
            overlap=settings.chunk_overlap,
            chunk_floor=chunk_floor,
        )
        texts = [chunk["text"] for chunk in chunks]
        vectors = []
        for start in range(0, len(texts), 64):
            vectors.extend(embedder.embed_documents(texts[start : start + 64]))
        points = [
            {
                "id": str(uuid.uuid5(uuid.NAMESPACE_URL, chunk["chunk_id"])),
                "vector": vector,
                "payload": build_payload(
                    chunk,
                    document,
                    {
                        "description": description,
                    },
                ),
            }
            for chunk, vector in zip(chunks, vectors)
        ]
        store.upsert(points)
        total_chunks += len(points)
    print(f"  ingested {len(UPLOADS)} docs / {total_chunks} chunks into {collection_name}")
    return store


def _rank_rows(store: VectorStore, embedder: OllamaClient, query_rows: List[Dict], top_k: int, margin: float) -> List[Dict]:
    rows = []
    for case in query_rows:
        vec = embedder.embed_query(case["query"])
        hits = store.search(vec, 15, case.get("tags"))
        ranked = [(h["payload"].get("filename"), h["score"]) for h in hits]
        kept = ranked[:top_k]
        if kept and margin > 0:
            cutoff = kept[0][1] - margin
            kept = [r for r in kept if r[1] >= cutoff]
        rows.append({**case, "ranked": ranked, "kept": kept})
    return rows


def _retrieval_metrics(rows: List[Dict]) -> Dict:
    p1 = recall = 0
    kept_counts = []
    for row in rows:
        kept = row["kept"]
        kept_counts.append(len(kept))
        files = [f for f, _ in kept]
        if files and files[0] in row["expected"]:
            p1 += 1
        if any(f in row["expected"] for f in files):
            recall += 1
    n = len(rows)
    return {
        "p1": (p1, n),
        "recall": (recall, n),
        "avg_kept": statistics.mean(kept_counts) if kept_counts else 0,
    }


def _build_pipeline(settings: Settings) -> RagPipeline:
    store = VectorStore(settings.qdrant_url, settings.collection_name, settings.vector_size, settings.distance)
    llm = _build_embedder(settings)
    retriever = Retriever(store, llm, settings)
    return RagPipeline(retriever, llm, settings)


def _answer_metrics(pipeline: RagPipeline, cases: List[Dict], negatives: List[Dict]) -> Dict:
    correct = scored = cited = citable = refused = 0
    latencies: List[float] = []
    for case in cases:
        t0 = time.time()
        result = pipeline.answer(case["query"], None, case.get("tags"))
        dt = time.time() - t0
        latencies.append(dt)
        ans = result["answer"]
        cite_ok = _has_citation(ans)
        if case.get("expect_refusal"):
            ok = _is_refusal(ans)
            refused += int(ok)
            scored += 1
            correct += int(ok)
        elif case.get("checks", {}).get("informational"):
            # informational probes are tracked via latency only
            pass
        else:
            citable += 1
            cited += int(cite_ok)
            ok = _must_include_ok(ans, case.get("checks", {}).get("must_include", []))
            correct += int(ok)
            scored += 1
    for neg in negatives:
        result = pipeline.answer(neg["query"], None, neg.get("tags"))
        refused += int(_is_refusal(result["answer"]))
    return {
        "correctness": (correct, scored),
        "citation": (cited, citable),
        "refusal": (refused, len(negatives)),
        "latency": latencies,
    }


def _fmt_ratio(num: int, den: int) -> str:
    return f"{num}/{den} ({(100 * num / den):.0f}%)" if den else "n/a"


def _print_run(name: str, retrieval: Dict, answers: Dict | None) -> None:
    print(f"{name}")
    print(f"  retrieval P@1:    {_fmt_ratio(*retrieval['p1'])}")
    print(f"  retrieval recall: {_fmt_ratio(*retrieval['recall'])}")
    print(f"  avg kept chunks:  {retrieval['avg_kept']:.1f}")
    if answers:
        c, cn = answers["correctness"]
        ci, cin = answers["citation"]
        r, rn = answers["refusal"]
        print(f"  answer correct:   {_fmt_ratio(c, cn)}")
        print(f"  citation cover:   {_fmt_ratio(ci, cin)}")
        print(f"  refusal accuracy: {_fmt_ratio(r, rn)}")
        if answers["latency"]:
            print(
                f"  latency/query:    mean {statistics.mean(answers['latency']):.1f}s  "
                f"median {statistics.median(answers['latency']):.1f}s  "
                f"max {max(answers['latency']):.1f}s"
            )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--baseline-floor", type=int, default=0)
    ap.add_argument("--candidate-floor", type=int, default=128)
    ap.add_argument("--baseline-collection", default="dffrnt_bench_baseline")
    ap.add_argument("--candidate-collection", default="dffrnt_bench_candidate")
    ap.add_argument("--limit", type=int, help="only use the first N answer cases")
    ap.add_argument(
        "--retrieval-only",
        action="store_true",
        help="skip answer generation and report only retrieval metrics",
    )
    ap.add_argument("--no-negatives", action="store_true", help="skip refusal probes")
    args = ap.parse_args()

    base = load_settings()
    query_cases = list(CASES) + [c for c in TAG_CASES if c.get("expected")]
    if args.limit:
        query_cases = query_cases[: args.limit]
    negatives = [] if args.no_negatives else list(NEGATIVE_CASES)
    top_k = base.top_k
    margin = base.score_margin
    embedder = _build_embedder(base)

    print("=== Chunk Benchmark ===")
    print(f"top_k={top_k}  score_margin={margin}  model={base.llm_model}  embed={base.embed_model}\n")

    runs = [
        ("baseline", args.baseline_collection, args.baseline_floor),
        ("candidate", args.candidate_collection, args.candidate_floor),
    ]
    results = {}
    for label, collection, floor in runs:
        settings = _build_settings(base, collection, floor)
        store = _ingest_corpus(settings, collection, floor)
        rows = _rank_rows(store, embedder, query_cases, top_k, margin)
        retrieval = _retrieval_metrics(rows)
        answers = None
        if not args.retrieval_only:
            pipeline = _build_pipeline(settings)
            answers = _answer_metrics(pipeline, query_cases, negatives)
        results[label] = (retrieval, answers)
        print()
        _print_run(label, retrieval, answers)

    print("\n=== Delta (candidate - baseline) ===")
    base_ret, base_ans = results["baseline"]
    cand_ret, cand_ans = results["candidate"]
    base_p1 = base_ret["p1"]
    cand_p1 = cand_ret["p1"]
    base_rec = base_ret["recall"]
    cand_rec = cand_ret["recall"]
    print(f"retrieval P@1:    {cand_p1[0]-base_p1[0]:+d} correct hits (den={base_p1[1]})")
    print(f"retrieval recall: {cand_rec[0]-base_rec[0]:+d} correct docs (den={base_rec[1]})")
    print(f"avg kept chunks:  {cand_ret['avg_kept'] - base_ret['avg_kept']:+.1f}")
    if not args.retrieval_only and base_ans and cand_ans:
        for key in ("correctness", "citation", "refusal"):
            b_num, b_den = base_ans[key]
            c_num, c_den = cand_ans[key]
            print(f"{key}: {b_num}/{b_den} -> {c_num}/{c_den}")


if __name__ == "__main__":
    main()

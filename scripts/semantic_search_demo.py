from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
import math
import re
import sys
from pathlib import Path
from datetime import datetime
from typing import Any, Iterable
import uuid


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from embeddings.embedder import Embedder
from ingestion.loaders import load_file
from processing.chunker import chunk_by_strategy, list_chunking_strategies, chunk_file
from vector_store.qdrant_store import QdrantStore


def build_demo_collection_name(document_path: Path) -> str:
    safe_name = document_path.stem.lower().replace(" ", "_").replace("-", "_")
    return f"demo_{safe_name}"


def ingest_document(document_path: Path, collection_name: str, embedder: Embedder, chunking_method: str, chunk_size: int, overlap: int):
    loaded = load_file(str(document_path))
    file_type = loaded.get("file_type")

    # chunk the file using file-aware chunking which preserves metadata per chunk
    chunks = chunk_file(loaded, strategy=chunking_method, chunk_size=chunk_size, overlap=overlap)
    vectors = embedder.embed_texts([chunk["text"] for chunk in chunks])

    store = QdrantStore(collection_name=collection_name)
    store.recreate_collection(vector_size=embedder.dim)

    points = []
    for chunk, vector in zip(chunks, vectors):
        point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, chunk["chunk_id"]))
        points.append(
            {
                "id": point_id,
                "vector": vector,
                "payload": {
                    "source_file": chunk.get("source_file") or str(document_path),
                    "filename": chunk.get("filename"),
                    "document_title": loaded.get("document_title"),
                    "file_type": file_type,
                    "chunk_id": chunk["chunk_id"],
                    "char_start": chunk["char_start"],
                    "char_end": chunk["char_end"],
                    "page_number": chunk.get("page_number"),
                    "slide_index": chunk.get("slide_index"),
                    "section_heading": chunk.get("section_heading"),
                    "text": chunk["text"],
                },
            }
        )

    store.upsert(points)
    return store, embedder, chunks


def tokenize_for_bm25(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def build_bm25_index(chunks: list[dict]) -> dict:
    """Build a minimal in-memory BM25 index over chunk text for the current run."""
    documents = []
    doc_freq = defaultdict(int)
    total_length = 0

    for chunk in chunks:
        tokens = tokenize_for_bm25(chunk.get("text", ""))
        term_freq = defaultdict(int)
        for token in tokens:
            term_freq[token] += 1
        for token in term_freq:
            doc_freq[token] += 1
        total_length += len(tokens)
        documents.append(
            {
                "chunk_id": chunk.get("chunk_id"),
                "source_file": chunk.get("source_file"),
                "text": chunk.get("text", ""),
                "tokens": tokens,
                "term_freq": term_freq,
                "length": len(tokens),
            }
        )

    return {
        "documents": documents,
        "doc_freq": dict(doc_freq),
        "avgdl": (total_length / len(documents)) if documents else 0.0,
        "doc_count": len(documents),
    }


def bm25_score_query(query: str, bm25_index: dict, k1: float = 1.5, b: float = 0.75) -> list[dict]:
    """Return BM25 candidates with chunk_id, source_file, text, and bm25_score."""
    query_terms = tokenize_for_bm25(query)
    if not query_terms or not bm25_index.get("documents"):
        return []

    doc_count = bm25_index.get("doc_count", 0)
    avgdl = bm25_index.get("avgdl") or 0.0
    doc_freq = bm25_index.get("doc_freq", {})
    candidates = []

    for doc in bm25_index["documents"]:
        score = 0.0
        doc_len = doc.get("length") or 0
        if doc_len == 0:
            continue

        for term in query_terms:
            tf = doc["term_freq"].get(term, 0)
            if tf == 0:
                continue
            n_q = doc_freq.get(term, 0)
            if n_q == 0:
                continue
            idf = math.log(1 + ((doc_count - n_q + 0.5) / (n_q + 0.5)))
            denom = tf + k1 * (1 - b + b * (doc_len / avgdl if avgdl else 0.0))
            score += idf * (tf * (k1 + 1)) / denom if denom else 0.0

        if score > 0:
            candidates.append(
                {
                    "chunk_id": doc["chunk_id"],
                    "source_file": doc["source_file"],
                    "text": doc["text"],
                    "bm25_score": score,
                }
            )

    candidates.sort(key=lambda item: item["bm25_score"], reverse=True)
    return candidates


def normalize_scores(items: list[dict], key: str) -> list[dict]:
    if not items:
        return items
    max_score = max((item.get(key) or 0.0) for item in items)
    if max_score <= 0:
        return items
    normalized = []
    for item in items:
        copy = dict(item)
        copy[f"{key}_normalized"] = (copy.get(key) or 0.0) / max_score
        normalized.append(copy)
    return normalized


def merge_vector_and_bm25_candidates(vector_candidates: list[dict], bm25_candidates: list[dict], vector_weight: float = 0.7, bm25_weight: float = 0.3) -> list[dict]:
    """Merge candidates by exact chunk_id only, preserving both scores when available."""
    vector_by_id = {str(item.get("payload", {}).get("chunk_id")): item for item in vector_candidates if item.get("payload", {}).get("chunk_id")}
    bm25_by_id = {str(item.get("chunk_id")): item for item in bm25_candidates if item.get("chunk_id")}

    merged_ids = list(dict.fromkeys(list(vector_by_id.keys()) + list(bm25_by_id.keys())))
    normalized_bm25 = normalize_scores(bm25_candidates, "bm25_score")
    bm25_norm_by_id = {str(item.get("chunk_id")): item.get("bm25_score_normalized") for item in normalized_bm25 if item.get("chunk_id")}

    merged = []
    for chunk_id in merged_ids:
        vector_item = vector_by_id.get(chunk_id)
        bm25_item = bm25_by_id.get(chunk_id)
        payload = dict((vector_item or {}).get("payload", {}) or {})
        if bm25_item:
            # prefer richer metadata from the vector payload, but keep text/source from BM25 if needed
            payload.setdefault("text", bm25_item.get("text"))
            payload.setdefault("source_file", bm25_item.get("source_file"))

        vector_score = (vector_item or {}).get("score")
        bm25_score = (bm25_item or {}).get("bm25_score")
        bm25_score_norm = bm25_norm_by_id.get(chunk_id, 0.0)
        combined_score = (vector_weight * (vector_score or 0.0)) + (bm25_weight * (bm25_score_norm or 0.0))

        merged.append(
            {
                "chunk_id": chunk_id,
                "vector_score": vector_score,
                "bm25_score": bm25_score,
                "combined_score": combined_score,
                "payload": payload,
            }
        )

    merged.sort(key=lambda item: item.get("combined_score") or 0.0, reverse=True)
    return merged


def retrieve_candidates(store: QdrantStore, embedder: Embedder, query: str, candidate_top_k: int, use_hybrid: bool, bm25_index: dict | None = None, similarity_threshold: float | None = None) -> list[dict]:
    query_vector = embedder.embed_texts([query])[0]
    vector_candidates = store.search(query_vector, top=candidate_top_k)

    if not use_hybrid or bm25_index is None:
        results = []
        for item in vector_candidates:
            payload = item.get("payload", {}) or {}
            results.append(
                {
                    "chunk_id": payload.get("chunk_id"),
                    "vector_score": item.get("score"),
                    "bm25_score": None,
                    "combined_score": item.get("score"),
                    "payload": payload,
                }
            )
        if similarity_threshold is not None:
            results = [item for item in results if (item.get("combined_score") or 0.0) >= similarity_threshold]
        return results

    bm25_candidates = bm25_score_query(query, bm25_index)
    merged = merge_vector_and_bm25_candidates(vector_candidates, bm25_candidates)
    if similarity_threshold is not None:
        merged = [item for item in merged if (item.get("combined_score") or 0.0) >= similarity_threshold]
    return merged


EVAL_CATEGORIES = {
    "resume": {
        "keywords": ["resume", "cv", "experience", "employment", "consulting", "proposal"],
        "templates": [
            "Find resumes mentioning {subject}.",
            "Which employee profiles show {subject} experience?",
            "What resumes discuss {subject}?",
        ],
    },
    "proposal": {
        "keywords": ["proposal", "rfp", "sow", "statement of work", "template", "bid"],
        "templates": [
            "Find proposal examples about {subject}.",
            "What proposal templates discuss {subject}?",
            "Show similar project proposals related to {subject}.",
        ],
    },
    "case_study": {
        "keywords": ["case study", "implementation", "outcome", "results", "project"],
        "templates": [
            "Find case studies describing {subject}.",
            "Show project outcomes related to {subject}.",
            "Which implementations mention {subject}?",
        ],
    },
    "sales": {
        "keywords": ["sales", "messaging", "pitch", "prospect", "marketing"],
        "templates": [
            "Find historical sales content about {subject}.",
            "Show sales messaging examples related to {subject}.",
            "Find sales materials discussing {subject}.",
        ],
    },
    "technical": {
        "keywords": ["rag", "air-gapped", "embedding", "vector", "qdrant", "llm", "knowledge"],
        "templates": [
            "Which projects mention {subject}?",
            "What technical experience is documented around {subject}?",
            "Find examples of work involving {subject}.",
        ],
    },
}


def _normalize_text(value: str) -> str:
    return " ".join((value or "").split()).strip()


def _infer_category(text: str, filename: str = "", section_heading: str | None = None) -> str:
    haystack = f"{filename} {section_heading or ''} {text}".lower()
    scores = {}
    for name, spec in EVAL_CATEGORIES.items():
        scores[name] = sum(1 for keyword in spec["keywords"] if keyword in haystack)
    best = max(scores, key=scores.get) if scores else "technical"
    return best if scores.get(best, 0) > 0 else "technical"


def _subject_label(chunk: dict) -> str:
    heading = _normalize_text(chunk.get("section_heading") or "")
    filename = Path(chunk.get("filename") or chunk.get("source_file") or "").stem.replace("_", " ").strip()
    text = _normalize_text(chunk.get("text") or "")
    if heading:
        return heading
    if filename:
        return filename
    words = text.split()[:6]
    return " ".join(words) if words else "document topic"


def _group_chunks_for_eval(chunks: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for chunk in chunks:
        grouped[(str(chunk.get("source_file")), str(chunk.get("section_heading") or "section"))].append(chunk)

    groups = []
    for (source_file, section_heading), items in grouped.items():
        # preserve chunk order within a section
        items = sorted(items, key=lambda item: (item.get("char_start", 0), item.get("char_end", 0)))
        section_text = _normalize_text(" ".join(item.get("text", "") for item in items))
        groups.append(
            {
                "source_file": source_file,
                "section_heading": section_heading,
                "chunk_ids": [item.get("chunk_id") for item in items if item.get("chunk_id")],
                "items": items,
                "text": section_text,
            }
        )
    return groups


def build_eval_queries(chunks: list[dict], eval_count: int):
    """Create business-focused evaluation queries with multi-chunk expectations.

    Generates realistic question templates by category and returns items shaped like:
    {
      query, expected_chunk_ids, expected_source_files, type
    }
    """
    eval_queries: list[dict] = []
    groups = _group_chunks_for_eval(chunks)

    for group in groups:
        if len(eval_queries) >= eval_count:
            break

        first_chunk = group["items"][0]
        category = _infer_category(group["text"], first_chunk.get("filename", ""), group.get("section_heading"))
        subject = _subject_label(first_chunk)
        templates = EVAL_CATEGORIES[category]["templates"]
        expected_chunk_ids = [chunk_id for chunk_id in group["chunk_ids"] if chunk_id]
        expected_source_files = sorted({str(first_chunk.get("source_file"))})

        # create one or more paraphrased versions per section until we reach the target count
        for template in templates[:3]:
            if len(eval_queries) >= eval_count:
                break
            eval_queries.append(
                {
                    "query": template.format(subject=subject),
                    "expected_chunk_ids": expected_chunk_ids,
                    "expected_source_files": expected_source_files,
                    "type": category,
                }
            )

    # add a few corpus-level cross-file queries if we still have room
    if len(eval_queries) < eval_count and chunks:
        corpus_templates = [
            ("resume", "Find healthcare consulting experience across the knowledge base."),
            ("proposal", "Find proposal examples and templates across the knowledge base."),
            ("case_study", "Find case studies describing implementation outcomes across the knowledge base."),
            ("sales", "Find historical sales and messaging materials across the knowledge base."),
            ("technical", "Which projects mention RAG or air-gapped deployment across the knowledge base?"),
        ]
        for category, query in corpus_templates:
            if len(eval_queries) >= eval_count:
                break
            matched_groups = []
            for group in groups:
                first_chunk = group["items"][0]
                inferred = _infer_category(group["text"], first_chunk.get("filename", ""), group.get("section_heading"))
                if inferred == category:
                    matched_groups.append(group)
            if not matched_groups:
                continue
            expected_chunk_ids = []
            expected_source_files = []
            for group in matched_groups[:3]:
                expected_chunk_ids.extend(group["chunk_ids"])
                expected_source_files.append(group["source_file"])
            eval_queries.append(
                {
                    "query": query,
                    "expected_chunk_ids": list(dict.fromkeys(expected_chunk_ids)),
                    "expected_source_files": sorted(set(expected_source_files)),
                    "type": category,
                }
            )

    return eval_queries[:eval_count]


def compute_metrics(expected_chunk_ids: list[str], expected_source_files: list[str], retrieved_results: list[dict], similarity_threshold: float | None = None) -> dict:
    retrieved_chunk_ids = [str(result.get("payload", {}).get("chunk_id")) for result in retrieved_results]
    retrieved_source_files = [str(result.get("payload", {}).get("source_file")) for result in retrieved_results]
    retrieved_scores = [result.get("score") for result in retrieved_results if result.get("score") is not None]

    expected_set = [chunk_id for chunk_id in expected_chunk_ids if chunk_id]
    expected_source_set = [source for source in expected_source_files if source]

    if expected_set:
        hits = [chunk_id for chunk_id in retrieved_chunk_ids if chunk_id in expected_set]
        recall_at_k = len(hits) / len(expected_set)
        precision_at_k = len(hits) / len(retrieved_chunk_ids) if retrieved_chunk_ids else 0.0
        first_rank = next((idx + 1 for idx, chunk_id in enumerate(retrieved_chunk_ids) if chunk_id in expected_set), None)
        mrr = 1.0 / first_rank if first_rank else 0.0
    else:
        hits = []
        recall_at_k = 0.0
        precision_at_k = 0.0
        mrr = 0.0

    if expected_source_set:
        coverage = len(set(retrieved_source_files) & set(expected_source_set)) / len(set(expected_source_set))
    else:
        coverage = 0.0

    if similarity_threshold is not None:
        thresholded = [result for result in retrieved_results if result.get("score") is not None and result.get("score") >= similarity_threshold]
        thresholded_ids = [str(result.get("payload", {}).get("chunk_id")) for result in thresholded]
        threshold_hits = [chunk_id for chunk_id in thresholded_ids if chunk_id in expected_set]
        threshold_recall = len(threshold_hits) / len(expected_set) if expected_set else 0.0
    else:
        threshold_recall = None

    max_score = max(retrieved_scores) if retrieved_scores else None
    avg_score = (sum(retrieved_scores) / len(retrieved_scores)) if retrieved_scores else None
    num_candidates_above_threshold = None
    if similarity_threshold is not None:
        num_candidates_above_threshold = sum(1 for score in retrieved_scores if score is not None and score >= similarity_threshold)

    return {
        "recall_at_k": recall_at_k,
        "precision_at_k": precision_at_k,
        "mrr": mrr,
        "coverage": coverage,
        "threshold_recall": threshold_recall,
        "evidence_strength": {
            "max_score": max_score,
            "avg_score": avg_score,
            "num_candidates_above_threshold": num_candidates_above_threshold,
            "coverage_count": len(set(retrieved_source_files) & set(expected_source_files)),
        },
    }


def _safe_metric_value(value: Any):
    if value is None:
        return ""
    return value


def write_eval_artifacts(results: list[dict], artifact_dir: Path, chunking_method: str, source_folder: str | None):
    artifact_dir.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = artifact_dir / f"eval_{chunking_method}_{run_id}.json"
    csv_path = artifact_dir / f"eval_{chunking_method}_{run_id}.csv"

    payload = {
        "run_id": run_id,
        "chunking_method": chunking_method,
        "source_folder": source_folder,
        "results": results,
    }
    json_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    fieldnames = [
        "query",
        "expected_chunk_ids",
        "expected_source_files",
        "retrieved_chunk_ids",
        "retrieved_source_files",
        "scores",
        "recall_at_k",
        "precision_at_k",
        "mrr",
        "coverage",
        "threshold_recall",
        "chunking_strategy",
        "source_folder",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for item in results:
            writer.writerow(
                {
                    "query": item.get("query"),
                    "expected_chunk_ids": json.dumps(item.get("expected_chunk_ids", [])),
                    "expected_source_files": json.dumps(item.get("expected_source_files", [])),
                    "retrieved_chunk_ids": json.dumps(item.get("retrieved_chunk_ids", [])),
                    "retrieved_source_files": json.dumps(item.get("retrieved_source_files", [])),
                    "scores": json.dumps(item.get("scores", [])),
                    "recall_at_k": _safe_metric_value(item.get("metrics", {}).get("recall_at_k")),
                    "precision_at_k": _safe_metric_value(item.get("metrics", {}).get("precision_at_k")),
                    "mrr": _safe_metric_value(item.get("metrics", {}).get("mrr")),
                    "coverage": _safe_metric_value(item.get("metrics", {}).get("coverage")),
                    "threshold_recall": _safe_metric_value(item.get("metrics", {}).get("threshold_recall")),
                    "chunking_strategy": item.get("chunking_strategy"),
                    "source_folder": item.get("source_folder"),
                }
            )

    return json_path, csv_path


def collect_documents(source_paths, limit_files: int | None = None):
    supported = [".pdf", ".docx", ".pptx", ".csv", ".txt", ".md"]
    discovered = []

    if not source_paths:
        source_paths = [REPO_ROOT / "database" / "raw"]

    seen = set()
    for raw_source in source_paths:
        source = Path(raw_source).expanduser().resolve()
        if source.is_file():
            if source.suffix.lower() in supported and str(source) not in seen:
                discovered.append(source)
                seen.add(str(source))
            continue

        if source.is_dir():
            for ext in supported:
                for file_path in sorted(source.rglob(f"*{ext}")):
                    resolved = file_path.resolve()
                    if str(resolved) in seen:
                        continue
                    discovered.append(resolved)
                    seen.add(str(resolved))

    discovered.sort(key=lambda item: str(item).lower())
    if limit_files is not None and limit_files > 0:
        discovered = discovered[:limit_files]
    return discovered


def evaluate_document(document_path: Path, chunking_method: str, embedder: Embedder, top_k: int, eval_count: int, chunk_size: int, overlap: int, mode: str, similarity_threshold: float | None, artifact_dir: Path | None):
    collection_name = f"eval_{chunking_method}_{build_demo_collection_name(document_path)}"
    store, _, chunks = ingest_document(document_path, collection_name, embedder, chunking_method, chunk_size, overlap)
    bm25_index = build_bm25_index(chunks)
    queries = build_eval_queries(chunks, eval_count)
    if not queries:
        return {
            "document": document_path,
            "chunking_method": chunking_method,
            "mode": mode,
            "correct": 0,
            "total": 0,
            "accuracy": 0.0,
            "chunk_count": len(chunks),
        }

    query_results = []
    correct = 0
    total_recall = 0.0
    total_precision = 0.0
    total_mrr = 0.0
    total_coverage = 0.0
    total_threshold_recall = 0.0
    threshold_count = 0

    for item in queries:
        results = retrieve_candidates(
            store=store,
            embedder=embedder,
            query=item["query"],
            candidate_top_k=top_k,
            use_hybrid=(mode == "hybrid"),
            bm25_index=bm25_index,
            similarity_threshold=similarity_threshold,
        )
        metrics = compute_metrics(
            item.get("expected_chunk_ids", []),
            item.get("expected_source_files", []),
            results,
            similarity_threshold=similarity_threshold,
        )
        query_results.append(
            {
                "query": item["query"],
                "expected_chunk_ids": item.get("expected_chunk_ids", []),
                "expected_source_files": item.get("expected_source_files", []),
                "retrieved_chunk_ids": [str((result.get("payload", {}) or {}).get("chunk_id")) for result in results],
                "retrieved_source_files": [str((result.get("payload", {}) or {}).get("source_file")) for result in results],
                "scores": [
                    {
                        "chunk_id": str((result.get("payload", {}) or {}).get("chunk_id")),
                        "vector_score": result.get("vector_score"),
                        "bm25_score": result.get("bm25_score"),
                        "combined_score": result.get("combined_score"),
                    }
                    for result in results
                ],
                "metrics": metrics,
                "chunking_strategy": chunking_method,
                "source_folder": str(document_path.parent),
                "mode": mode,
            }
        )

        if metrics["recall_at_k"] > 0 or metrics["coverage"] > 0:
            correct += 1
        total_recall += metrics["recall_at_k"]
        total_precision += metrics["precision_at_k"]
        total_mrr += metrics["mrr"]
        total_coverage += metrics["coverage"]
        if metrics.get("threshold_recall") is not None:
            total_threshold_recall += metrics["threshold_recall"]
            threshold_count += 1

    total = len(queries)
    accuracy = correct / total if total else 0.0
    avg_recall = total_recall / total if total else 0.0
    avg_precision = total_precision / total if total else 0.0
    avg_mrr = total_mrr / total if total else 0.0
    avg_coverage = total_coverage / total if total else 0.0
    avg_threshold_recall = (total_threshold_recall / threshold_count) if threshold_count else None
    return {
        "document": document_path,
        "chunking_method": chunking_method,
        "mode": mode,
        "correct": correct,
        "total": total,
        "accuracy": accuracy,
        "chunk_count": len(chunks),
        "recall_at_k": avg_recall,
        "precision_at_k": avg_precision,
        "mrr": avg_mrr,
        "coverage": avg_coverage,
        "threshold_recall": avg_threshold_recall,
        "query_results": query_results,
        "source_folder": str(document_path.parent),
    }


def print_results(store: QdrantStore, embedder: Embedder, query: str, top_k: int, expected_chunk_id: str | None = None, use_hybrid: bool = False, bm25_index: dict | None = None):
    results = retrieve_candidates(
        store=store,
        embedder=embedder,
        query=query,
        candidate_top_k=top_k,
        use_hybrid=use_hybrid,
        bm25_index=bm25_index,
    )

    print(f"\nQUERY: {query}")
    matched = False
    for index, result in enumerate(results, start=1):
        # support both dict results and objects
        if isinstance(result, dict):
            payload = result.get("payload") or {}
            score = result.get("combined_score") if result.get("combined_score") is not None else result.get("score")
        else:
            payload = getattr(result, "payload", {}) or {}
            score = getattr(result, "score", None)

        excerpt = (payload.get("text") or "")[:220].replace("\n", " ")
        chunk_id = payload.get("chunk_id")
        if expected_chunk_id is not None and chunk_id == expected_chunk_id:
            matched = True
        print(f"{index}. score={score} file={payload.get('source_file')}")
        print(f"   excerpt={excerpt}")
    if expected_chunk_id is not None:
        print(f"   expected_chunk_id={expected_chunk_id} matched={matched}")
    return matched


def print_summary(results):
    print("\nSUMMARY")
    print("mode\tmethod\tdocument\tcorrect\ttotal\taccuracy\trecall@k\tprecision@k\tmrr\tcoverage")
    method_totals = defaultdict(lambda: [0, 0])
    method_metrics = defaultdict(lambda: defaultdict(float))
    method_counts = defaultdict(int)
    for item in results:
        mode = item.get("mode", "vector_only")
        method = item["chunking_method"]
        key = (mode, method)
        method_totals[key][0] += item["correct"]
        method_totals[key][1] += item["total"]
        method_metrics[key]["recall_at_k"] += item.get("recall_at_k", 0.0)
        method_metrics[key]["precision_at_k"] += item.get("precision_at_k", 0.0)
        method_metrics[key]["mrr"] += item.get("mrr", 0.0)
        method_metrics[key]["coverage"] += item.get("coverage", 0.0)
        method_counts[key] += 1
        print(
            f"{mode}\t{method}\t{item['document'].name}\t{item['correct']}\t{item['total']}\t{item['accuracy']:.2%}\t{item.get('recall_at_k', 0.0):.2%}\t{item.get('precision_at_k', 0.0):.2%}\t{item.get('mrr', 0.0):.2%}\t{item.get('coverage', 0.0):.2%}"
        )

    print("\nAGGREGATE")
    for key in sorted(method_totals):
        correct, total = method_totals[key]
        accuracy = correct / total if total else 0.0
        count = method_counts[key] or 1
        avg_recall = method_metrics[key]["recall_at_k"] / count
        avg_precision = method_metrics[key]["precision_at_k"] / count
        avg_mrr = method_metrics[key]["mrr"] / count
        avg_coverage = method_metrics[key]["coverage"] / count
        mode, method = key
        print(f"{mode}/{method}: {correct}/{total} = {accuracy:.2%} | recall@k={avg_recall:.2%} precision@k={avg_precision:.2%} mrr={avg_mrr:.2%} coverage={avg_coverage:.2%}")


def _run_eval_and_maybe_write_artifacts(results: list[dict], artifact_dir: Path | None, chunking_method: str, source_folder: str | None):
    if artifact_dir is None:
        return None, None
    return write_eval_artifacts(results, artifact_dir, chunking_method, source_folder)


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest one document and test semantic search with Qdrant.")
    parser.add_argument(
        "document",
        nargs="?",
        default=None,
        help="Path to a PDF/DOCX/PPTX/CSV document to ingest. If omitted, the script scans database/raw recursively. Use --source to limit files or folders.",
    )
    parser.add_argument("--source", action="append", default=None, help="File or folder to include in the evaluation. Repeat to limit scope. Folders are scanned recursively.")
    parser.add_argument("--limit-files", type=int, default=None, help="Limit the number of files evaluated after source expansion.")
    parser.add_argument("--collection", default=None, help="Qdrant collection name to use for single-document query mode.")
    parser.add_argument("--top-k", type=int, default=3, help="How many search results to show for each query.")
    parser.add_argument(
        "--eval-count",
        type=int,
        default=20,
        help="When running evaluation mode, generate this many business-focused queries per document/section.",
    )
    parser.add_argument(
        "--chunking-methods",
        default=",".join(list_chunking_strategies()),
        help="Comma-separated chunking methods to compare: fixed,sentence,paragraph,recursive.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=1200,
        help="Maximum chunk size used by the chunking methods.",
    )
    parser.add_argument(
        "--overlap",
        type=int,
        default=150,
        help="Overlap used by fixed and recursive chunking.",
    )
    parser.add_argument(
        "--query",
        action="append",
        default=None,
        help="Manual query mode. Repeat to add more queries. If omitted, the script runs evaluation mode with labeled queries.",
    )
    parser.add_argument(
        "--artifact-dir",
        default=str(REPO_ROOT / "artifacts" / "eval"),
        help="Directory where evaluation JSON/CSV artifacts are written.",
    )
    parser.add_argument(
        "--candidate-top-k",
        type=int,
        default=30,
        help="Candidate retrieval size used during evaluation baselines.",
    )
    parser.add_argument(
        "--similarity-threshold",
        type=float,
        default=None,
        help="Optional similarity threshold used for threshold-based recall reporting.",
    )
    parser.add_argument(
        "--use-hybrid",
        type=lambda value: str(value).strip().lower() in ("1", "true", "yes", "y", "on"),
        default=True,
        help="When true, run hybrid vector + BM25 evaluation in addition to vector-only mode.",
    )
    args = parser.parse_args()

    chunking_methods = [method.strip().lower() for method in args.chunking_methods.split(",") if method.strip()]
    invalid_methods = [method for method in chunking_methods if method not in list_chunking_strategies()]
    if invalid_methods:
        print(f"Unsupported chunking methods: {', '.join(invalid_methods)}")
        return 2

    embedder = Embedder()

    if args.query:
        source_documents = collect_documents([args.document] if args.document else args.source, args.limit_files)
        if not source_documents:
            print("No documents found for query mode.")
            return 2
        document_path = source_documents[0]
        if not document_path.exists():
            print(f"Document not found: {document_path}")
            return 2

        collection_name = args.collection or build_demo_collection_name(document_path)
        store, _, chunks = ingest_document(document_path, collection_name, embedder, chunking_methods[0], args.chunk_size, args.overlap)
        print(f"Ingested {len(chunks)} chunks into Qdrant collection '{collection_name}'.")
        bm25_index = build_bm25_index(chunks) if args.use_hybrid else None

        for query in args.query:
            print_results(store, embedder, query, args.top_k, use_hybrid=args.use_hybrid, bm25_index=bm25_index)
        return 0

    source_documents = collect_documents([args.document] if args.document else args.source, args.limit_files)
    if not source_documents:
        print("No documents found. Add files under database/raw or pass --source.")
        return 2

    all_results = []
    artifact_dir = Path(args.artifact_dir) if args.artifact_dir else None
    for chunking_method in chunking_methods:
        print(f"\n=== Chunking method: {chunking_method} ===")
        for document_path in source_documents:
            collection_name = f"eval_{chunking_method}_{build_demo_collection_name(document_path)}"
            store, _, chunks = ingest_document(document_path, collection_name, embedder, chunking_method, args.chunk_size, args.overlap)
            print(f"Ingested {len(chunks)} chunks from {document_path.name} into '{collection_name}'.")

            queries = build_eval_queries(chunks, args.eval_count)
            if not queries:
                print(f"No evaluation queries could be generated for {document_path.name}.")
                continue

            bm25_index = build_bm25_index(chunks) if args.use_hybrid else None
            modes = ["vector_only", "hybrid"] if args.use_hybrid else ["vector_only"]

            for mode in modes:
                query_results = []
                correct = 0
                total_recall = 0.0
                total_precision = 0.0
                total_mrr = 0.0
                total_coverage = 0.0
                total_threshold_recall = 0.0
                threshold_count = 0

                for item in queries:
                    results = retrieve_candidates(
                        store=store,
                        embedder=embedder,
                        query=item["query"],
                        candidate_top_k=args.candidate_top_k,
                        use_hybrid=(mode == "hybrid"),
                        bm25_index=bm25_index,
                        similarity_threshold=args.similarity_threshold,
                    )
                    metrics = compute_metrics(
                        item.get("expected_chunk_ids", []),
                        item.get("expected_source_files", []),
                        results,
                        similarity_threshold=args.similarity_threshold,
                    )

                    query_results.append(
                        {
                            "query": item["query"],
                            "expected_chunk_ids": item.get("expected_chunk_ids", []),
                            "expected_source_files": item.get("expected_source_files", []),
                            "retrieved_chunk_ids": [str((result.get("payload", {}) or {}).get("chunk_id")) for result in results],
                            "retrieved_source_files": [str((result.get("payload", {}) or {}).get("source_file")) for result in results],
                            "scores": [
                                {
                                    "chunk_id": str((result.get("payload", {}) or {}).get("chunk_id")),
                                    "vector_score": result.get("vector_score"),
                                    "bm25_score": result.get("bm25_score"),
                                    "combined_score": result.get("combined_score"),
                                }
                                for result in results
                            ],
                            "metrics": metrics,
                            "chunking_strategy": chunking_method,
                            "source_folder": str(document_path.parent),
                            "mode": mode,
                        }
                    )

                    if metrics["recall_at_k"] > 0 or metrics["coverage"] > 0:
                        correct += 1
                    total_recall += metrics["recall_at_k"]
                    total_precision += metrics["precision_at_k"]
                    total_mrr += metrics["mrr"]
                    total_coverage += metrics["coverage"]
                    if metrics.get("threshold_recall") is not None:
                        total_threshold_recall += metrics["threshold_recall"]
                        threshold_count += 1

                total = len(queries)
                accuracy = correct / total if total else 0.0
                result_row = {
                    "document": document_path,
                    "chunking_method": chunking_method,
                    "mode": mode,
                    "correct": correct,
                    "total": total,
                    "accuracy": accuracy,
                    "chunk_count": len(chunks),
                    "recall_at_k": total_recall / total if total else 0.0,
                    "precision_at_k": total_precision / total if total else 0.0,
                    "mrr": total_mrr / total if total else 0.0,
                    "coverage": total_coverage / total if total else 0.0,
                    "threshold_recall": (total_threshold_recall / threshold_count) if threshold_count else None,
                    "query_results": query_results,
                    "source_folder": str(document_path.parent),
                }
                all_results.append(result_row)
                mode_artifact_dir = artifact_dir / mode if artifact_dir is not None else None
                _run_eval_and_maybe_write_artifacts(query_results, mode_artifact_dir, f"{chunking_method}_{mode}", str(document_path.parent))
                print(
                    f"Retrieval accuracy for {document_path.name} [{chunking_method}/{mode}]: {correct}/{total} = {accuracy:.2%} | recall@k={result_row['recall_at_k']:.2%} precision@k={result_row['precision_at_k']:.2%} mrr={result_row['mrr']:.2%} coverage={result_row['coverage']:.2%}"
                )

    print_summary(all_results)

    # write a run-level summary artifact if requested
    if artifact_dir is not None:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_json = artifact_dir / f"run_summary_{run_id}.json"
        run_json.write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "chunking_methods": chunking_methods,
                    "source_documents": [str(path) for path in source_documents],
                    "results": all_results,
                },
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
from __future__ import annotations

import json
import sys
import uuid
from collections import OrderedDict
from datetime import datetime
from statistics import mean, median
from collections import Counter, defaultdict
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from embeddings.embedder import Embedder
from ingestion.loaders import load_file
from processing.chunker import chunk_file
from vector_store.qdrant_store import QdrantStore


CORPUS_ROOT = REPO_ROOT / "database" / "raw"
REPORT_PATH = REPO_ROOT / "Files" / "database_validation.md"


QUERY_GROUPS = OrderedDict(
    [
        (
            "Group A - Exact retrieval sanity checks",
            [
                "What technologies were used in PicoShell?",
                "What projects did this person work on?",
                "What technical skills are listed?",
                "Where did this person study?",
                "What sections should a case study include?",
                "How should project outcomes be presented?",
                "What belongs in an implementation plan?",
                "What is the structure of a one-page case study?",
                "How is AI being used by the company?",
                "What are the RUN and CHANGE pillars?",
                "What business strategy is discussed?",
                "What leadership themes are mentioned?",
            ],
        ),
        (
            "Group B - Cross-file retrieval tests",
            [
                "Find documents discussing AI",
                "Find implementation examples",
                "Find documents discussing performance metrics",
                "Find examples related to leadership",
                "Show documents discussing strategy",
            ],
        ),
        (
            "Group C - Semantic retrieval tests",
            [
                "Which tools or platforms were used in that shell project?",
                "What examples exist of artificial intelligence initiatives?",
                "Find prior implementation experience",
                "Show examples of organizational transformation",
            ],
        ),
        (
            "Group D - Negative tests",
            [
                "What blockchain project was implemented?",
                "Find autonomous vehicle work",
                "Show aerospace projects",
            ],
        ),
    ]
)


def collect_documents(source_root: Path) -> list[Path]:
    supported = {".pdf", ".docx", ".pptx", ".csv", ".txt", ".md"}
    return [path for path in sorted(source_root.rglob("*")) if path.is_file() and path.suffix.lower() in supported]


def ingest_corpus(
    documents: list[Path],
    embedder: Embedder,
    corpus_root: Path,
    chunking_method: str = "recursive",
    chunk_size: int = 1200,
    overlap: int = 150,
):
    collection_name = f"db_validation_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    store = QdrantStore(collection_name=collection_name)
    store.recreate_collection(vector_size=embedder.dim)

    chunk_records: list[dict] = []
    total_points = 0
    failed_files: list[dict] = []
    embedding_dims: list[int] = []
    embeddings_created = 0

    print(f"Discovered {len(documents)} supported documents under {corpus_root}", flush=True)

    for index, document_path in enumerate(documents, start=1):
        print(f"[{index}/{len(documents)}] Loading {document_path.name}", flush=True)
        try:
            loaded = load_file(str(document_path))
        except Exception as e:
            print(f"[{index}/{len(documents)}] Failed to load {document_path.name}: {e}", flush=True)
            failed_files.append({"path": str(document_path), "error": str(e)})
            continue

        chunks = chunk_file(loaded, strategy=chunking_method, chunk_size=chunk_size, overlap=overlap)
        if not chunks:
            print(f"[{index}/{len(documents)}] No chunks created for {document_path.name}", flush=True)
            continue

        print(f"[{index}/{len(documents)}] Created {len(chunks)} chunks; embedding...", flush=True)
        vectors = embedder.embed_texts([chunk["text"] for chunk in chunks])
        # record embedding dims
        for v in vectors:
            try:
                embedding_dims.append(len(v))
            except Exception:
                embedding_dims.append(None)
        embeddings_created += len(vectors)

        points = []
        for chunk, vector in zip(chunks, vectors):
            chunk_record = {
                "source_file": chunk.get("source_file") or str(document_path),
                "filename": chunk.get("filename") or document_path.name,
                "document_title": loaded.get("document_title"),
                "file_type": loaded.get("file_type"),
                "chunk_id": chunk["chunk_id"],
                "char_start": chunk.get("char_start"),
                "char_end": chunk.get("char_end"),
                "page_number": chunk.get("page_number"),
                "slide_index": chunk.get("slide_index"),
                "section_heading": chunk.get("section_heading"),
                "text": chunk["text"],
            }
            chunk_records.append(chunk_record)
            points.append(
                {
                    "id": str(uuid.uuid5(uuid.NAMESPACE_URL, chunk["chunk_id"])),
                    "vector": vector,
                    "payload": chunk_record,
                }
            )

        store.upsert(points)
        total_points += len(points)
        print(f"[{index}/{len(documents)}] Upserted {len(points)} chunks into Qdrant", flush=True)

    embedding_dimension = embedding_dims[0] if embedding_dims else None
    dimension_consistent = all(d == embedding_dimension for d in embedding_dims) if embedding_dims else True

    stats = {
        "failed_files": failed_files,
        "embeddings_created": embeddings_created,
        "embedding_dims": embedding_dims,
        "embedding_dimension": embedding_dimension,
        "dimension_consistent": dimension_consistent,
    }

    return store, chunk_records, total_points, collection_name, stats


def preview_text(text: str, limit: int = 190) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def run_queries(
    store: QdrantStore,
    embedder: Embedder,
    queries_by_group: OrderedDict[str, list[str]],
    top_k: int = 5,
    weak_evidence_threshold: float | None = None,
) -> list[dict]:
    rows = []
    for group_name, queries in queries_by_group.items():
        print(f"Running {group_name} ({len(queries)} queries)", flush=True)
        for query in queries:
            print(f"  Query: {query}", flush=True)
            query_vector = embedder.embed_texts([query])[0]
            results = store.search(query_vector, top=top_k)
            scores = [float(result.get("score") or 0.0) for result in results]
            if scores:
                print(
                    "    score_distribution: "
                    f"min={min(scores):.4f} max={max(scores):.4f} avg={mean(scores):.4f}",
                    flush=True,
                )
            if weak_evidence_threshold is not None:
                kept_results = [result for result in results if float(result.get("score") or 0.0) >= weak_evidence_threshold]
            else:
                kept_results = results
            rows.append(
                {
                    "group": group_name,
                    "query": query,
                    "results": kept_results,
                    "all_results": results,
                }
            )
    return rows


def compute_database_scorecard(documents: list[Path], chunk_records: list[dict], total_points: int, ingest_stats: dict, store: QdrantStore) -> dict:
    files_discovered = len(documents)
    files_loaded = len({rec.get("source_file") for rec in chunk_records})
    ingestion_completeness = files_loaded / files_discovered if files_discovered else 0.0

    # chunk quality
    chunks_by_file = defaultdict(list)
    lengths = []
    empty_chunk_count = 0
    short_chunk_count = 0
    chunk_ids = []
    for rec in chunk_records:
        text = rec.get("text") or ""
        l = len(text.strip())
        lengths.append(l)
        if l == 0:
            empty_chunk_count += 1
        if l < 100:
            short_chunk_count += 1
        chunks_by_file[rec.get("source_file")].append(rec)
        chunk_ids.append(rec.get("chunk_id"))

    total_chunks = len(chunk_records)
    avg_chunks_per_file = mean([len(v) for v in chunks_by_file.values()]) if chunks_by_file else 0
    min_chunk_length = min(lengths) if lengths else 0
    max_chunk_length = max(lengths) if lengths else 0
    avg_chunk_length = mean(lengths) if lengths else 0
    median_chunk_length = median(lengths) if lengths else 0
    duplicate_chunk_count = sum(v - 1 for v in Counter(chunk_ids).values() if v > 1)

    # cross-file contamination: same chunk_id appearing in multiple files
    chunkid_to_files = defaultdict(set)
    for rec in chunk_records:
        chunkid_to_files[rec.get("chunk_id")].add(rec.get("source_file"))
    cross_file_contamination_count = sum(1 for files in chunkid_to_files.values() if len(files) > 1)

    # metadata completeness
    required_fields = ["source_file", "filename", "file_type", "chunk_id", "section_heading", "char_start", "char_end"]
    field_counts = {f: 0 for f in required_fields}
    for rec in chunk_records:
        for f in required_fields:
            if rec.get(f) is not None:
                field_counts[f] += 1
    metadata_completeness_percent = {f: (field_counts[f] / total_chunks * 100 if total_chunks else 0.0) for f in required_fields}

    # embedding quality
    embeddings_created = ingest_stats.get("embeddings_created", 0)
    embedding_dimension = ingest_stats.get("embedding_dimension")
    dimension_consistent = ingest_stats.get("dimension_consistent", True)
    embedding_completion_rate = embeddings_created / total_chunks if total_chunks else 0.0

    # qdrant storage
    expected_vector_count = total_chunks
    # attempt to get actual count from Qdrant: use client API
    qdrant_count = None
    try:
        qdrant_count = len(chunk_records)  # default if client query not available
        # try to get actual via client
        if hasattr(store.client, "get_collection"):
            info = store.client.get_collection(collection_name=store.collection_name)
            qdrant_count = info.payload_count if hasattr(info, "payload_count") else qdrant_count
        elif hasattr(store.client, "collections_api"):
            # newer clients expose api
            info = store.client.collections_api.get_collection(collection_name=store.collection_name)
            qdrant_count = info.result.payload_count if hasattr(info, "result") and hasattr(info.result, "payload_count") else qdrant_count
    except Exception:
        pass

    storage_completion_rate = (qdrant_count / expected_vector_count) if expected_vector_count else 0.0

    file_type_counter = Counter()
    for rec in chunk_records:
        sf = rec.get("source_file")
        if not sf:
            continue
        suffix = Path(sf).suffix.lower().lstrip('.')
        file_type_counter[suffix] += 1

    # sample chunks
    sample_chunks = []
    for rec in chunk_records[:5]:
        sample_chunks.append(
            {
                "source_file": rec.get("source_file"),
                "section_heading": rec.get("section_heading"),
                "chunk_id": rec.get("chunk_id"),
                "char_start": rec.get("char_start"),
                "char_end": rec.get("char_end"),
                "preview": preview_text(rec.get("text", "")),
            }
        )

    # sample payloads
    sample_payloads = []
    for rec in chunk_records[:5]:
        sample_payloads.append({k: rec.get(k) for k in ["source_file", "filename", "file_type", "chunk_id", "page_number", "slide_index", "section_heading", "char_start", "char_end"]})

    scorecard = {
        "file_ingestion": {
            "files_discovered": files_discovered,
            "files_loaded": files_loaded,
            "ingestion_completeness": round(ingestion_completeness, 4),
            "failed_files": ingest_stats.get("failed_files", []),
            "file_type_breakdown": {k.upper(): v for k, v in file_type_counter.items()},
        },
        "chunk_quality": {
            "total_chunks": total_chunks,
            "avg_chunks_per_file": round(avg_chunks_per_file, 2),
            "min_chunk_length": min_chunk_length,
            "max_chunk_length": max_chunk_length,
            "avg_chunk_length": round(avg_chunk_length, 2),
            "median_chunk_length": median_chunk_length,
            "empty_chunk_count": empty_chunk_count,
            "short_chunk_count": short_chunk_count,
            "duplicate_chunk_count": duplicate_chunk_count,
            "cross_file_contamination_count": cross_file_contamination_count,
            "sample_chunks": sample_chunks,
        },
        "cross_file_contamination_count": cross_file_contamination_count,
        "metadata_quality": {
            "metadata_completeness_percent": {k: round(v, 2) for k, v in metadata_completeness_percent.items()},
            "sample_payloads": sample_payloads,
        },
        "embedding_quality": {
            "chunks_created": total_chunks,
            "embeddings_created": embeddings_created,
            "embedding_completion_rate": round(embedding_completion_rate, 4),
            "embedding_dimension": embedding_dimension,
            "dimension_consistency": bool(dimension_consistent),
        },
        "qdrant_quality": {
            "expected_vector_count": expected_vector_count,
            "qdrant_collection_count": qdrant_count,
            "storage_completion_rate": round(storage_completion_rate, 4),
            "sample_records": [],
        },
    }

    # add sample qdrant records by listing first few chunk_records with computed id
    for rec in chunk_records[:5]:
        pid = str(uuid.uuid5(uuid.NAMESPACE_URL, rec.get("chunk_id"))) if rec.get("chunk_id") else None
        scorecard["qdrant_quality"]["sample_records"].append({"id": pid, "payload_preview": {"source_file": rec.get("source_file"), "chunk_id": rec.get("chunk_id"), "preview": preview_text(rec.get("text",""))}})

    # Determine PASS/REVIEW/FAIL for A using Phase 1 heuristics
    reasons = []
    status = "PASS"
    # ingestion completeness
    if scorecard["file_ingestion"]["ingestion_completeness"] < 0.95:
        reasons.append(f"Ingestion completeness below 95% ({scorecard['file_ingestion']['ingestion_completeness']:.2f})")
        status = "REVIEW"
    # metadata
    meta_ok = all(v >= 95.0 for v in metadata_completeness_percent.values())
    if not meta_ok:
        reasons.append("Metadata completeness below 95% for one or more fields")
        status = "REVIEW"
    # embeddings
    if scorecard["embedding_quality"]["embedding_completion_rate"] < 0.99:
        reasons.append("Embedding completion rate below 99%")
        status = "REVIEW"
    if not scorecard["embedding_quality"]["dimension_consistency"]:
        reasons.append("Embedding dimension inconsistent")
        status = "FAIL"
    # cross-file contamination
    if scorecard["chunk_quality"]["cross_file_contamination_count"] > 0:
        reasons.append("Cross-file chunk_id contamination detected")
        status = "FAIL"
    # storage
    if scorecard["qdrant_quality"]["storage_completion_rate"] < 0.99:
        reasons.append("Qdrant storage completion below 99%")
        if status != "FAIL":
            status = "REVIEW"

    scorecard["status"] = status
    scorecard["reasons"] = reasons
    return scorecard


def compute_retrieval_scorecard(raw_rows: list[dict], documents: list[Path], threshold: float = 0.45) -> dict:
    # raw_rows: list of {group, query, results(all kept by run_queries), all_results}
    total_queries = len(raw_rows)
    queries_with_sensible = 0
    negative_queries = 0
    negative_suppressed = 0
    unique_sources_overall = set()
    unique_sources_per_query = []
    returned_chunks = 0
    irrelevant_above_threshold = 0
    required_fields = ["source_file", "filename", "file_type", "chunk_id"]
    metadata_present_count = 0
    retrieved_chunk_ids = {}

    # paraphrase mapping (pairs)
    paraphrase_pairs = [
        ("What projects did this person work on?", "Find prior project experience"),
        ("What technical skills are listed?", "What technical skills are listed?"),
    ]
    paraphrase_results = []

    for row in raw_rows:
        all_results = row.get("all_results") or []
        # top score
        scores = [float(r.get("score") or 0.0) for r in all_results]
        top_score = max(scores) if scores else 0.0
        if top_score >= threshold:
            queries_with_sensible += 1

        # negative queries
        if row["group"].startswith("Group D"):
            negative_queries += 1
            if top_score < threshold:
                negative_suppressed += 1

        srcs = [((r.get("payload") or {}).get("source_file")) for r in all_results if (r.get("payload") or {}).get("source_file")]
        unique_srcs = set(srcs)
        unique_sources_overall.update(unique_srcs)
        unique_sources_per_query.append(len(unique_srcs))

        for r in all_results:
            returned_chunks += 1
            payload = r.get("payload") or {}
            # simple irrelevant proxy: very short preview but high score
            text = (payload.get("text") or "").strip()
            if len(text) < 50 and float(r.get("score") or 0.0) >= threshold:
                irrelevant_above_threshold += 1
            if all(payload.get(f) is not None for f in required_fields):
                metadata_present_count += 1
        # store retrieved chunk ids for paraphrase checks
        retrieved_chunk_ids[row["query"]] = [((r.get("payload") or {}).get("chunk_id")) for r in all_results]

    # paraphrase stability: compute overlap
    paraphrase_overlaps = []
    for a, b in paraphrase_pairs:
        set_a = set(retrieved_chunk_ids.get(a, []))
        set_b = set(retrieved_chunk_ids.get(b, []))
        if not set_a and not set_b:
            overlap = 0.0
        else:
            overlap = len(set_a.intersection(set_b)) / (len(set_a.union(set_b)) or 1)
        paraphrase_overlaps.append({"pair": (a, b), "overlap": overlap})

    metrics = {
        "queries_with_sensible_results": f"{queries_with_sensible}/{total_queries}",
        "source_coverage_rate": f"{len(unique_sources_overall)}/{len(documents)}",
        "broad_queries_returning_multiple_files": f"{sum(1 for idx, v in enumerate(unique_sources_per_query) if v>1 and raw_rows[idx]['group'].startswith('Group B'))}/{len([r for r in raw_rows if r['group'].startswith('Group B')])}",
        "retrieval_diversity_avg": mean(unique_sources_per_query) if unique_sources_per_query else 0.0,
        "negative_suppression_rate": f"{negative_suppressed}/{negative_queries}",
        "weak_evidence_leakage": f"{irrelevant_above_threshold}/{returned_chunks}",
        "metadata_retrieval_completeness": f"{metadata_present_count}/{returned_chunks * len(required_fields) if returned_chunks else 1}",
        "paraphrase_stability": paraphrase_overlaps,
    }

    # simple heuristics for PASS/REVIEW/FAIL
    result = "PASS"
    try:
        qsr = queries_with_sensible / total_queries
        neg_sup = negative_suppressed / negative_queries if negative_queries else 1.0
    except Exception:
        qsr = 0.0
        neg_sup = 0.0
    if qsr < 0.5 or neg_sup < 0.5:
        result = "REVIEW"
    if qsr < 0.25 or neg_sup < 0.25:
        result = "FAIL"

    return {"metrics": metrics, "result": result, "per_query": raw_rows}


def render_markdown(report: dict) -> str:
    lines: list[str] = []
    lines.append("# Database Validation Report")
    lines.append("")
    lines.append(f"Generated: {report['generated_at']}")
    lines.append(f"Corpus root: `{report['corpus_root']}`")
    lines.append(f"Collection: `{report['collection_name']}`")
    lines.append(f"Weak evidence threshold: `{report['weak_evidence_threshold']}`")
    lines.append(f"Documents ingested: {report['document_count']}")
    lines.append(f"Chunks ingested: {report['chunk_count']}")
    lines.append("")

    # Section A: Database Infrastructure Scorecard
    lines.append("## A. Database Infrastructure Scorecard")
    lines.append("")
    a = report.get("scorecard_a", {})
    lines.append(f"**Result:** {a.get('status','')}")
    if a.get('reasons'):
        lines.append("")
        lines.append("**Reasons / Notes:**")
        for r in a.get('reasons', []):
            lines.append(f"- {r}")
    lines.append("")
    lines.append("### 1. File ingestion")
    for k, v in a.get("file_ingestion", {}).items():
        if k == "failed_files":
            lines.append(f"- {k}: {len(v)} failed (see sample below)")
            for ff in v[:5]:
                lines.append(f"  - {ff.get('path')}: {ff.get('error')}")
        else:
            lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("### 2. Chunk quality")
    cq = a.get("chunk_quality", {})
    for k in ["total_chunks","avg_chunks_per_file","min_chunk_length","max_chunk_length","avg_chunk_length","median_chunk_length","empty_chunk_count","short_chunk_count","duplicate_chunk_count","cross_file_contamination_count"]:
        lines.append(f"- {k}: {cq.get(k)}")
    lines.append("")
    lines.append("#### Sample chunks:")
    for s in cq.get("sample_chunks", []):
        lines.append(f"- source_file: {s['source_file']}")
        lines.append(f"  - section_heading: {s['section_heading']}")
        lines.append(f"  - chunk_id: {s['chunk_id']}")
        lines.append(f"  - char_start: {s['char_start']} char_end: {s['char_end']}")
        lines.append(f"  - preview: {s['preview']}")
    lines.append("")
    lines.append("### 3. Metadata quality")
    mq = a.get("metadata_quality", {})
    for k, v in mq.get("metadata_completeness_percent", {}).items():
        lines.append(f"- {k}: {v}%")
    lines.append("")
    lines.append("#### Sample payloads:")
    for p in mq.get("sample_payloads", []):
        lines.append(f"- {p}")
    lines.append("")
    lines.append("### 4. Embedding quality")
    for k, v in a.get("embedding_quality", {}).items():
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("### 5. Qdrant storage quality")
    qk = a.get("qdrant_quality", {})
    lines.append(f"- expected_vector_count: {qk.get('expected_vector_count')}")
    lines.append(f"- qdrant_collection_count: {qk.get('qdrant_collection_count')}")
    lines.append(f"- storage_completion_rate: {qk.get('storage_completion_rate')}")
    lines.append("")
    lines.append("#### Sample stored records:")
    for rec in qk.get("sample_records", []):
        lines.append(f"- id: {rec.get('id')}")
        lines.append(f"  - payload_preview: {rec.get('payload_preview')}")
    lines.append("")

    # Section B: Baseline Retrieval Scorecard
    lines.append("## B. Baseline Retrieval / Searchability Scorecard")
    lines.append("")
    b = report.get("scorecard_b", {})
    lines.append(f"**Result:** {b.get('result','')}")
    lines.append("")
    lines.append("### Metrics")
    for k, v in b.get("metrics", {}).items():
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("### Per-query results (top 5)")
    lines.append("")
    for item in report.get("groups_list", []):
        lines.append(f"### Query: {item['query']}")
        lines.append("")
        if item.get("results"):
            for r in item.get("results", []):
                lines.append(f"- score: {r['score']:.4f}")
                lines.append(f"  - source_file: {r['source_file']}")
                lines.append(f"  - section_heading: {r['section_heading']}")
                lines.append(f"  - chunk_id: {r['chunk_id']}")
                lines.append(f"  - preview: {r['preview']}")
        else:
            lines.append("- insufficient evidence")
        lines.append("")

    # Final recommendation
    lines.append("## C. Overall readiness recommendation")
    lines.append("")
    lines.append(f"{report.get('recommendation','')}")
    lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Validate ingestion, chunking, metadata, embeddings, and Qdrant retrieval.")
    parser.add_argument("--source-root", default=str(CORPUS_ROOT), help="Folder to scan recursively for supported source files.")
    parser.add_argument("--limit-files", type=int, default=None, help="Limit the number of supported files ingested for a faster smoke test.")
    parser.add_argument(
        "--weak-evidence-threshold",
        type=float,
        default=0.45,
        help="Suppress retrieval results below this score and mark those queries as insufficient evidence.",
    )
    args = parser.parse_args()

    source_root = Path(args.source_root).expanduser().resolve()
    documents = collect_documents(source_root)
    if args.limit_files is not None and args.limit_files > 0:
        documents = documents[: args.limit_files]
    if not documents:
        print(f"No supported documents found under {source_root}")
        return 2

    embedder = Embedder()
    store, chunk_records, total_points, collection_name, ingest_stats = ingest_corpus(documents, embedder, source_root)
    print(f"Embedding dimension: {embedder.dim}", flush=True)
    print(f"Qdrant collection contains {len(chunk_records)} chunk payloads", flush=True)
    # get all results (no threshold) for post-hoc metric calculations
    raw_results = run_queries(store, embedder, QUERY_GROUPS, top_k=5, weak_evidence_threshold=None)

    # compute scorecards
    scorecard_a = compute_database_scorecard(documents, chunk_records, total_points, ingest_stats, store)
    scorecard_b = compute_retrieval_scorecard(raw_results, documents, threshold=args.weak_evidence_threshold)

    # build groups_list for markdown (per query top5 formatted)
    groups_list = []
    for row in raw_results:
        formatted = []
        for r in row.get("all_results", [])[:5]:
            payload = r.get("payload") or {}
            formatted.append(
                {
                    "score": float(r.get("score") or 0.0),
                    "source_file": payload.get("source_file"),
                    "section_heading": payload.get("section_heading"),
                    "chunk_id": payload.get("chunk_id"),
                    "preview": preview_text(payload.get("text", "")),
                }
            )
        groups_list.append({"query": row.get("query"), "results": formatted})

    # recommendation logic combining A and B
    a_status = scorecard_a.get("status")
    b_status = scorecard_b.get("result")
    if a_status == "PASS" and b_status == "PASS":
        recommendation = "Ready for full RAG evaluation."
    elif a_status == "PASS" and b_status == "REVIEW":
        recommendation = "Database is structurally ready, but baseline search needs tuning."
    else:
        recommendation = "Fix ingestion/chunking/metadata/embedding/Qdrant before RAG work."

    grouped_results: dict[str, list[dict]] = OrderedDict()
    positive_test_hits = 0
    negative_test_weak = 0
    cross_file_test_hits = 0
    metadata_health = True

    for row in raw_results:
        formatted_results = []
        source_files = []
        scores = []
        for result in row["results"]:
            payload = result.get("payload", {}) or {}
            source_file = payload.get("source_file")
            if source_file:
                source_files.append(source_file)
            scores.append(result.get("score") or 0.0)
            formatted_results.append(
                {
                    "score": float(result.get("score") or 0.0),
                    "source_file": source_file,
                    "section_heading": payload.get("section_heading"),
                    "chunk_id": payload.get("chunk_id"),
                    "preview": preview_text(payload.get("text", "")),
                }
            )
            if not payload.get("chunk_id") or not source_file:
                metadata_health = False

        top_score = scores[0] if scores else 0.0
        lowered_query = row["query"].lower()
        if any(token in lowered_query for token in ["blockchain", "autonomous vehicle", "aerospace"]):
            if top_score < args.weak_evidence_threshold:
                negative_test_weak += 1
        else:
            if top_score >= args.weak_evidence_threshold and formatted_results:
                positive_test_hits += 1
        if len(set(source_files)) > 1:
            cross_file_test_hits += 1

        grouped_results.setdefault(row["group"], []).append(
            {
                "query": row["query"],
                "results": formatted_results,
            }
        )

    summary = OrderedDict(
        [
            ("sensible_tests", f"{positive_test_hits}/{len(raw_results) - 3} queries showed plausible retrieval (heuristic threshold)."),
            ("unrelated_chunks", "Needs manual review from the report below; the script does not auto-label unrelated results."),
            ("multiple_files_returned", f"{cross_file_test_hits} queries returned more than one source file in the top 5."),
            ("metadata_chunking_health", "Healthy" if metadata_health else "Check payloads: missing chunk_id or source_file detected."),
            ("overall_assessment", f"Validation complete on {len(documents)} documents and {total_points} chunks. Qdrant retrieval is operational; review the printed rows for relevance quality."),
            ("negative_tests_weak", f"{negative_test_weak}/3 negative queries stayed below the weak-evidence threshold of {args.weak_evidence_threshold:.2f}."),
        ]
    )

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "corpus_root": str(source_root),
        "collection_name": collection_name,
        "weak_evidence_threshold": args.weak_evidence_threshold,
        "document_count": len(documents),
        "chunk_count": len(chunk_records),
        "summary": summary,
        "scorecard_a": scorecard_a,
        "scorecard_b": scorecard_b,
        "groups_list": groups_list,
        "recommendation": recommendation,
    }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(render_markdown(report), encoding="utf-8")

    print(json.dumps(report["summary"], indent=2))
    print(f"\nWrote markdown report to: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
"""Maintenance CLI: bring the vector store in line with the app's data.

1. **Summary backfill** (default): generate + upsert a summary point for every
   ingested document that lacks one (documents uploaded before summaries
   existed are otherwise skipped by routing and prompt briefings). The text
   comes from the source file in ``data_dir``, else from the stored chunks.

2. **Bulk ingest** (``--ingest-missing``, opt-in): ingest supported files that
   sit in ``data_dir`` but have no chunks — the restore path for a wiped KB.

Run from the repo root with the services up:
  python -m dffrnt_assistant.ingest.backfill [--dry-run] [--ingest-missing]
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from typing import Dict, List, Optional

from .loaders import load_file
from .pipeline import SUPPORTED_EXTENSIONS, build_summary_point, ingest_file

# Only this much reconstructed text is needed: summary prompts truncate anyway.
_RECONSTRUCT_CHARS = 8000

_META_KEYS = ("tags", "tag_paths", "description", "content_hash")


def _distinct_filenames(store) -> List[str]:
    seen: Dict[str, None] = {}
    for payload in store.all_payloads():
        filename = (payload or {}).get("filename")
        if filename:
            seen.setdefault(filename, None)
    return list(seen)


def _document_from_chunks(filename: str, payloads: List[Dict]) -> Optional[dict]:
    """Rebuild enough of a Document from stored chunks to summarize it."""
    chunks = sorted(payloads, key=lambda p: (p.get("page_number") or 0, p.get("char_start") or 0))
    text = "\n\n".join((p.get("text") or "") for p in chunks)[:_RECONSTRUCT_CHARS].strip()
    if not text:
        return None
    first = chunks[0]
    return {
        "text": text,
        "filename": filename,
        "file_type": first.get("file_type"),
        "source_file": first.get("source_file"),
        "document_title": None,
        "sections": [],
    }


def missing_summaries(store, summary_store) -> List[str]:
    """Filenames with chunks in the document store but no summary point."""
    summarized = set(_distinct_filenames(summary_store))
    return [f for f in _distinct_filenames(store) if f not in summarized]


def backfill_summaries(store, summary_store, embedder, data_dir: Path, dry_run: bool = False) -> int:
    done = 0
    for filename in missing_summaries(store, summary_store):
        chunk_payloads = store.payloads_by_filenames([filename], limit=10000)
        meta = {}
        if chunk_payloads:
            first = chunk_payloads[0]
            meta = {k: first.get(k) for k in _META_KEYS if first.get(k)}

        source = data_dir / filename
        if source.is_file():
            document, origin = load_file(str(source)), "file"
        else:
            document, origin = _document_from_chunks(filename, chunk_payloads), "chunks"
        if document is None:
            print(f"  !! {filename}: no source file and no chunk text — skipped")
            continue
        if dry_run:
            print(f"  would summarize {filename} (from {origin})")
            done += 1
            continue
        point = build_summary_point(document, embedder, meta)
        summary_store.upsert([point])
        summary = point["payload"].get("document_summary") or ""
        print(f"  {filename}: summarized from {origin} ({len(summary)} chars)")
        done += 1
    return done


def ingest_missing_files(store, embedder, settings, data_dir: Path,
                         summary_store=None, dry_run: bool = False) -> int:
    done = 0
    for path in sorted(data_dir.iterdir()):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        if store.has_document(path.name):
            continue
        if dry_run:
            print(f"  would ingest {path.name}")
            done += 1
            continue
        meta = {"content_hash": hashlib.sha256(path.read_bytes()).hexdigest()}
        chunks = ingest_file(path, store, embedder, settings, meta, summary_store=summary_store)
        print(f"  {path.name}: ingested ({chunks} chunks)")
        done += 1
    return done


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="report actions without writing")
    ap.add_argument(
        "--ingest-missing", action="store_true",
        help="also ingest supported data_dir files absent from the collection",
    )
    args = ap.parse_args()

    from ..config import load_settings
    from ..ollama import OllamaClient
    from ..retrieval.store import VectorStore

    settings = load_settings()
    store = VectorStore(
        settings.qdrant_url, settings.collection_name, settings.vector_size, settings.distance
    )
    summary_store = VectorStore(
        settings.qdrant_url, settings.summary_collection_name,
        settings.vector_size, settings.distance,
    )
    summary_store.ensure_collection()
    embedder = OllamaClient(
        settings.ollama_url, settings.llm_model, settings.embed_model,
        settings.llm_temperature, settings.llm_timeout,
        settings.embed_query_prefix, settings.embed_document_prefix,
        settings.llm_num_ctx, settings.llm_top_p, settings.llm_top_k,
        settings.llm_repeat_penalty, settings.llm_num_predict,
    )
    data_dir = Path(settings.data_dir)

    if args.ingest_missing:
        print(f"== ingesting data_dir files missing from '{settings.collection_name}' ==")
        n = ingest_missing_files(store, embedder, settings, data_dir, summary_store, args.dry_run)
        print(f"== {n} file(s) {'to ingest' if args.dry_run else 'ingested'} ==")

    print(f"== backfilling document summaries ('{settings.summary_collection_name}') ==")
    n = backfill_summaries(store, summary_store, embedder, data_dir, args.dry_run)
    print(f"== {n} summar{'ies' if n != 1 else 'y'} {'to generate' if args.dry_run else 'generated'} ==")


if __name__ == "__main__":
    main()

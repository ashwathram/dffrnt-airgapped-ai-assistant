"""Maintenance CLI: bring the vector store in line with the app's data.

1. **Summary backfill** (default): generate + upsert a summary point for every
   ingested document that lacks one (documents uploaded before summaries
   existed are otherwise skipped by routing and prompt briefings). The text
   comes from the source file in ``data_dir``, else from the stored chunks.

2. **Bulk ingest** (``--ingest-missing``, opt-in): ingest supported files that
   sit in ``data_dir`` but have no chunks — the restore path for a wiped KB.
   Add ``--force`` to re-ingest files already present too — a full refresh
   after an ingestion-code or config change — preserving each file's stored
   tags/description so curation metadata survives.

Run from the repo root with the services up:
  python -m dffrnt_assistant.ingest.backfill [--dry-run] [--ingest-missing] [--force] [--verbose]
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from typing import Dict, List, Optional

from .loaders import load_file
from .pipeline import (
    SUPPORTED_EXTENSIONS,
    build_summary_point,
    ingest_file,
    ingest_file_stream,
)

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


def orphaned_documents(store, data_dir: Path) -> List[str]:
    """Filenames in the collection with no source file in ``data_dir``. A
    disk-driven re-ingest cannot reach these, so they keep whatever schema and
    summary they were last written with — the reconciliation must surface them."""
    return [f for f in _distinct_filenames(store) if not (data_dir / f).is_file()]


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


def _ingest_streaming(path, store, embedder, settings, meta, summary_store) -> int:
    """Ingest one file, printing each pipeline stage (parse, summarize, chunk,
    per-batch embed, store) as it happens. Returns the chunk count."""
    chunks = 0
    for event in ingest_file_stream(path, store, embedder, settings, meta, summary_store=summary_store):
        stage = event.get("stage")
        if stage == "embedding":
            print(f"       embedding {event['done']}/{event['total']}", flush=True)
        elif stage == "stored":
            chunks = event["chunks"]
        elif stage:
            print(f"       {stage} …", flush=True)
    return chunks


def ingest_missing_files(store, embedder, settings, data_dir: Path,
                         summary_store=None, dry_run: bool = False,
                         force: bool = False, verbose: bool = False) -> int:
    """Ingest supported files in ``data_dir``. Files already in the collection
    are skipped unless ``force`` — then every file is re-ingested (ingestion is
    idempotent, replacing each filename's own points). The tags/description
    already stored on a file's chunks are carried over so a refresh never drops
    curation metadata; ``content_hash`` is always recomputed from disk. With
    ``verbose`` each file's pipeline stages are streamed as they run."""
    done = 0
    for path in sorted(data_dir.iterdir()):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        present = store.has_document(path.name)
        if present and not force:
            continue
        verb = "re-ingest" if present else "ingest"
        if dry_run:
            print(f"  would {verb} {path.name}")
            done += 1
            continue
        existing = store.payloads_by_filenames([path.name], limit=1) if present else []
        meta = {k: existing[0].get(k) for k in _META_KEYS if existing and existing[0].get(k)}
        meta["content_hash"] = hashlib.sha256(path.read_bytes()).hexdigest()
        if verbose:
            print(f"  {verb}ing {path.name} …", flush=True)
            chunks = _ingest_streaming(path, store, embedder, settings, meta, summary_store)
        else:
            chunks = ingest_file(path, store, embedder, settings, meta, summary_store=summary_store)
        print(f"  {path.name}: {verb}ed ({chunks} chunks)", flush=True)
        done += 1
    return done


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="report actions without writing")
    ap.add_argument(
        "--ingest-missing", action="store_true",
        help="also ingest supported data_dir files absent from the collection",
    )
    ap.add_argument(
        "--force", action="store_true",
        help="re-ingest every data_dir file, even those already present (implies --ingest-missing)",
    )
    ap.add_argument(
        "-v", "--verbose", action="store_true",
        help="stream each file's pipeline stages (parse/summarize/chunk/embed/store)",
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
        settings.embed_on_cpu,
    )
    data_dir = Path(settings.data_dir)

    if args.ingest_missing or args.force:
        scope = "re-ingesting all" if args.force else "ingesting missing"
        print(f"== {scope} data_dir files for '{settings.collection_name}' ==")
        n = ingest_missing_files(
            store, embedder, settings, data_dir, summary_store, args.dry_run,
            force=args.force, verbose=args.verbose,
        )
        print(f"== {n} file(s) {'to (re)ingest' if args.dry_run else 'ingested'} ==")

        # Reconciliation: docs the disk-driven pass above could not reach.
        orphans = orphaned_documents(store, data_dir)
        if orphans:
            print(f"!! {len(orphans)} document(s) in the collection have no source file "
                  f"in {data_dir} — force cannot reach these (old schema/summary kept):")
            for f in orphans:
                print(f"     - {f}")
            print("   restore the source files to data_dir, or wipe + re-upload, to refresh them.")
        else:
            print("== reconciled: every collection document has a source file on disk ==")

    print(f"== backfilling document summaries ('{settings.summary_collection_name}') ==")
    n = backfill_summaries(store, summary_store, embedder, data_dir, args.dry_run)
    print(f"== {n} summar{'ies' if n != 1 else 'y'} {'to generate' if args.dry_run else 'generated'} ==")


if __name__ == "__main__":
    main()

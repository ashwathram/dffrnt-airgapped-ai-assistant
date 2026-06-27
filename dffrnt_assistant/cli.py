"""Batch ingestion CLI.

Walks a folder and ingests every supported file through the *same* pipeline the
API upload route uses, into the *same* collection — so batch-loaded documents
are immediately queryable by the assistant.

    dffrnt-ingest --source-root database/raw [--metadata-file meta.json] [--limit N]
"""

import argparse
from pathlib import Path

from .config import load_settings
from .ingest.metadata import load_metadata_map
from .ingest.pipeline import SUPPORTED_EXTENSIONS, ingest_paths
from .ollama import OllamaClient
from .retrieval.store import VectorStore


def main() -> int:
    settings = load_settings()

    parser = argparse.ArgumentParser(description="Batch-ingest documents into the vector store")
    parser.add_argument("--source-root", default=settings.source_root)
    parser.add_argument("--metadata-file", default=None, help="Optional JSON/CSV metadata sidecar")
    parser.add_argument("--limit", type=int, default=None, help="Ingest at most N files")
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Drop and recreate the collection first (required when the embed model's "
        "vector dimension changes, e.g. switching to bge-m3). DESTROYS existing vectors.",
    )
    args = parser.parse_args()

    root = Path(args.source_root)
    if not root.exists():
        print(f"Source root not found: {root}")
        return 2

    store = VectorStore(
        settings.qdrant_url, settings.collection_name, settings.vector_size, settings.distance
    )
    if args.recreate:
        print(
            f"Recreating collection '{settings.collection_name}' at "
            f"{settings.vector_size}-dim for embed model '{settings.embed_model}'..."
        )
        store.recreate_collection()
    else:
        store.ensure_collection()
    embedder = OllamaClient(
        settings.ollama_url,
        settings.llm_model,
        settings.embed_model,
        settings.llm_temperature,
        settings.llm_timeout,
        settings.embed_query_prefix,
        settings.embed_document_prefix,
    )

    metadata_map = load_metadata_map(Path(args.metadata_file)) if args.metadata_file else None

    docs = [
        p
        for p in sorted(root.rglob("*"))
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
    ]
    if args.limit:
        docs = docs[: args.limit]

    print(f"Ingesting {len(docs)} file(s) from {root} into '{settings.collection_name}'...")
    total, failed = ingest_paths(docs, store, embedder, settings, metadata_map)
    print(f"Done: {total} chunks stored.")

    if failed:
        print(f"{len(failed)} file(s) failed:")
        for item in failed:
            print(f"  - {item['path']}: {item['error']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

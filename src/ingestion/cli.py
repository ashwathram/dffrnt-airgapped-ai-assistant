"""Production CLI entrypoint for the ingestion pipeline.

This script wires environment variables and CLI args to `ingest_corpus`.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Add src to path for imports
REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from embeddings.embedder import Embedder  # noqa: E402
from ingestion.destination import make_collection_name  # noqa: E402
from ingestion.ingest import ingest_corpus  # noqa: E402
from ingestion.metadata import load_metadata_map  # noqa: E402
from vector_store.qdrant_store import QdrantStore  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest documents into Qdrant with optional metadata sidecar"
    )
    parser.add_argument("--source-root", default=os.environ.get("SOURCE_ROOT", "database/raw"))
    parser.add_argument(
        "--qdrant-url", default=os.environ.get("QDRANT_URL", "http://localhost:6333")
    )
    parser.add_argument("--collection-name", default=os.environ.get("COLLECTION_NAME", None))
    parser.add_argument("--workspace", default=os.environ.get("WORKSPACE", None))
    parser.add_argument("--schema", default=os.environ.get("SCHEMA", None))
    parser.add_argument("--metadata-file", default=os.environ.get("METADATA_FILE", None))
    parser.add_argument(
        "--state-file", default=os.environ.get("STATE_FILE", ".cache/ingest_state.json")
    )
    parser.add_argument(
        "--incremental",
        action="store_true",
        default=os.environ.get("INCREMENTAL", "false").lower() in {"1", "true", "yes"},
    )
    parser.add_argument("--limit-files", type=int, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_root = Path(args.source_root)
    if not source_root.exists():
        print(f"Source root {source_root} not found", file=sys.stderr)
        return 2

    metadata_map = {}
    if args.metadata_file:
        metadata_map = load_metadata_map(Path(args.metadata_file))

    embedder = Embedder()
    collection_name = args.collection_name or make_collection_name(
        args.workspace, args.schema, Path(args.source_root).name
    )
    store = QdrantStore(url=args.qdrant_url, collection_name=collection_name)

    # collect documents
    supported = {".pdf", ".docx", ".pptx", ".csv", ".txt", ".md"}
    docs = [
        p for p in sorted(source_root.rglob("*")) if p.is_file() and p.suffix.lower() in supported
    ]
    if args.limit_files:
        docs = docs[: args.limit_files]

    state_file = Path(args.state_file)

    store, chunk_records, total_points, collection_name, stats = ingest_corpus(
        docs,
        embedder,
        source_root,
        store=store,
        incremental=args.incremental,
        state_path=state_file,
        metadata_map=metadata_map,
    )

    print(f"Ingested {total_points} chunks into collection {collection_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

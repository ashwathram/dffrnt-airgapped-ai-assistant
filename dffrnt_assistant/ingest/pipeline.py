"""The one ingestion pipeline: load -> chunk -> embed -> store.

Drives the API upload route, so every uploaded document is retrievable by the
assistant.
"""

import uuid
from pathlib import Path
from typing import Optional

from .chunker import chunk_file
from .loaders import load_file

# Single source of truth for what the system accepts (API validation + CLI scan).
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".pptx", ".xlsx", ".csv", ".txt", ".md"}

_METADATA_KEYS = (
    "document_type", "department", "client_project", "tags", "tag_paths",
    "description", "content_hash",
)


def build_payload(chunk: dict, document: dict, meta: Optional[dict] = None) -> dict:
    """Assemble the canonical Qdrant payload for a chunk (see schema.PAYLOAD_FIELDS)."""
    payload = {
        "text": chunk["text"],
        "source_file": chunk.get("source_file") or document.get("source_file"),
        "filename": chunk.get("filename") or document.get("filename"),
        "file_type": chunk.get("file_type") or document.get("file_type"),
        "page_number": chunk.get("page_number"),
        "slide_index": chunk.get("slide_index"),
        "section_heading": chunk.get("section_heading"),
        "chunk_id": chunk.get("chunk_id"),
        "char_start": chunk.get("char_start"),
        "char_end": chunk.get("char_end"),
        "document_type": None,
        "department": None,
        "client_project": None,
        "tags": [],
        "tag_paths": [],
        "description": "",
        "content_hash": "",
    }
    if meta:
        for key in _METADATA_KEYS:
            if meta.get(key) is not None:
                payload[key] = meta[key]
    return payload


EMBED_BATCH = 64  # embed in bounded batches so progress can be reported per batch


def ingest_file_stream(path, store, embedder, settings, meta: Optional[dict] = None):
    """Load, chunk, embed and store a single file, yielding progress events.

    Yields dicts keyed by ``stage``:
        {"stage": "parsing"}
        {"stage": "chunking"}
        {"stage": "embedding", "done": i, "total": n}   (once per embed batch)
        {"stage": "storing"}
        {"stage": "stored", "chunks": n}                 (terminal)

    Embedding progress is real: texts are embedded in batches of EMBED_BATCH and
    an event is emitted after each, so the caller can drive a progress bar that
    tracks the slow (embedding) stage rather than guessing.

    Idempotent: existing chunks for the same filename are removed first, so
    re-ingesting an updated document never leaves stale chunks behind.
    """
    path = Path(path)
    yield {"stage": "parsing"}
    document = load_file(str(path))

    yield {"stage": "chunking"}
    chunks = chunk_file(
        document,
        strategy=settings.chunk_strategy,
        chunk_size=settings.chunk_size,
        overlap=settings.chunk_overlap,
    )
    total = len(chunks)
    if not total:
        yield {"stage": "stored", "chunks": 0}
        return

    texts = [chunk["text"] for chunk in chunks]
    vectors: list = []
    yield {"stage": "embedding", "done": 0, "total": total}
    for start in range(0, total, EMBED_BATCH):
        # Slicing to EMBED_BATCH bounds each call, so the embedder's own batching
        # is a no-op here; we call it plainly for embedder-implementation parity.
        vectors.extend(embedder.embed_documents(texts[start : start + EMBED_BATCH]))
        yield {"stage": "embedding", "done": min(start + EMBED_BATCH, total), "total": total}

    points = [
        {
            "id": str(uuid.uuid5(uuid.NAMESPACE_URL, chunk["chunk_id"])),
            "vector": vector,
            "payload": build_payload(chunk, document, meta),
        }
        for chunk, vector in zip(chunks, vectors)
    ]

    yield {"stage": "storing"}
    store.delete_by_filename(document.get("filename") or path.name)
    store.upsert(points)
    yield {"stage": "stored", "chunks": len(points)}


def ingest_file(path, store, embedder, settings, meta: Optional[dict] = None) -> int:
    """Load, chunk, embed and store a single file. Returns the chunk count.

    Thin wrapper over :func:`ingest_file_stream` for callers that only need the
    final count (the CLI scan and the non-streaming upload path).
    """
    count = 0
    for event in ingest_file_stream(path, store, embedder, settings, meta):
        if event.get("stage") == "stored":
            count = event["chunks"]
    return count

"""The one ingestion pipeline: load -> chunk -> embed -> store.

Used identically by the API upload route and the batch CLI, so a document
ingested either way is retrievable by the assistant.
"""

import uuid
from pathlib import Path
from typing import Iterable, List, Optional

from .chunker import chunk_file
from .loaders import load_file

# Single source of truth for what the system accepts (API validation + CLI scan).
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".pptx", ".xlsx", ".csv", ".txt", ".md"}

_METADATA_KEYS = ("document_type", "department", "client_project", "tags", "tag_paths")


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
    }
    if meta:
        for key in _METADATA_KEYS:
            if meta.get(key) is not None:
                payload[key] = meta[key]
    return payload


def ingest_file(path, store, embedder, settings, meta: Optional[dict] = None) -> int:
    """Load, chunk, embed and store a single file. Returns the chunk count.

    Idempotent: existing chunks for the same filename are removed first, so
    re-ingesting an updated document never leaves stale chunks behind.
    """
    path = Path(path)
    document = load_file(str(path))
    chunks = chunk_file(
        document,
        strategy=settings.chunk_strategy,
        chunk_size=settings.chunk_size,
        overlap=settings.chunk_overlap,
    )
    if not chunks:
        return 0

    vectors = embedder.embed_texts([chunk["text"] for chunk in chunks])
    points = [
        {
            "id": str(uuid.uuid5(uuid.NAMESPACE_URL, chunk["chunk_id"])),
            "vector": vector,
            "payload": build_payload(chunk, document, meta),
        }
        for chunk, vector in zip(chunks, vectors)
    ]

    store.delete_by_filename(document.get("filename") or path.name)
    store.upsert(points)
    return len(points)


def ingest_paths(
    paths: Iterable,
    store,
    embedder,
    settings,
    metadata_map: Optional[dict] = None,
) -> tuple[int, List[dict]]:
    """Ingest many files. Returns (total_chunks, failed) where failed is a list
    of ``{"path", "error"}`` dicts so one bad file never aborts the batch."""
    total = 0
    failed: List[dict] = []
    for path in paths:
        path = Path(path)
        meta = None
        if metadata_map:
            meta = metadata_map.get(str(path)) or metadata_map.get(path.name)
        try:
            total += ingest_file(path, store, embedder, settings, meta)
        except Exception as exc:
            failed.append({"path": str(path), "error": str(exc)})
    return total, failed

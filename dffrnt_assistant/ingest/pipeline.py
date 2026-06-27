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
    "description", "uploaded_by", "content_hash",
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
        "uploaded_by": "",
        "content_hash": "",
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

    vectors = embedder.embed_documents([chunk["text"] for chunk in chunks])
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

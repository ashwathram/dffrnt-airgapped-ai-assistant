"""The one ingestion pipeline: load -> summarize -> chunk -> embed -> store."""

import re
import uuid
from pathlib import Path
from typing import Optional

from .chunker import chunk_file
from .loaders import load_file

# Single source of truth for what the system accepts.
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".pptx", ".xlsx", ".csv", ".txt", ".md"}

EMBED_BATCH = 64  # embed in bounded batches so progress can be reported per batch

_METADATA_KEYS = (
    "document_type", "department", "client_project", "tags", "tag_paths",
    "description", "content_hash", "document_summary", "summary_kind",
)

# Chunker fallback headings ("section3") carry no signal — never embed them.
_PLACEHOLDER_HEADING = re.compile(r"^section\d+$")


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
        "document_summary": "",
        "summary_kind": "chunk",
    }
    if meta:
        for key in _METADATA_KEYS:
            if meta.get(key) is not None:
                payload[key] = meta[key]
    return payload


def _context_line(parts) -> str:
    """Join non-empty, de-duplicated parts into one ' · ' context line."""
    cleaned = []
    for part in parts:
        part = (part or "").strip()
        if part and part not in cleaned:
            cleaned.append(part)
    return " · ".join(cleaned)


def chunk_embed_text(chunk: dict, document: dict) -> str:
    """The text actually embedded for a chunk: a filename/title/heading context
    line, then the chunk text. The stored payload keeps the raw text — the
    prefix only anchors the embedding in vector space."""
    heading = chunk.get("section_heading") or ""
    if _PLACEHOLDER_HEADING.match(heading):
        heading = ""
    context = _context_line(
        [document.get("filename"), document.get("document_title"), heading]
    )
    text = chunk.get("text") or ""
    return f"{context}\n{text}" if context else text


def summary_embed_text(document: dict, summary: str, meta: Optional[dict] = None) -> str:
    """The text embedded for a document-summary point: filename, title and the
    user-entered description alongside the summary, so lexical anchors
    (candidate names, project titles) reach the routing signal."""
    context = _context_line(
        [
            document.get("filename"),
            document.get("document_title"),
            (meta or {}).get("description"),
        ]
    )
    summary = (summary or "").strip()
    if context and summary:
        return f"{context}\n{summary}"
    return summary or context or (document.get("filename") or "")


def build_summary_prompt(document: dict, max_chars: int = 6000) -> str:
    title = document.get("document_title") or document.get("filename") or "document"
    text = (document.get("text") or "").strip()[:max_chars]
    return (
        "Summarize the uploaded document for retrieval routing.\n"
        "Return 2-4 short sentences, plain text only.\n"
        "Focus on the document type, topic, named entities, and what a user might ask about.\n"
        "Do not invent facts.\n\n"
        f"Document title: {title}\n\n"
        f"Document text:\n{text}\n\n"
        "Summary:"
    )


def generate_document_summary(document: dict, llm) -> str:
    """A short LLM routing summary for a document; falls back to a leading
    excerpt if generation fails, so ingestion always continues. Thinking is
    disabled: a 2-4 sentence routing summary gains nothing from a reasoning
    pass, and skipping it cuts ingestion time per upload substantially."""
    text = (document.get("text") or "").strip()
    if not text:
        return ""
    try:
        summary = llm.generate(build_summary_prompt(document), think=False).strip()
    except Exception:
        summary = ""
    return summary or " ".join(text.split())[:400].rstrip()


def build_summary_point(document: dict, embedder, meta: Optional[dict] = None) -> dict:
    """Generate, embed and package a document-summary point (shared by the
    upload pipeline and the backfill CLI)."""
    summary = generate_document_summary(document, embedder)
    vector = embedder.embed_documents([summary_embed_text(document, summary, meta)])[0]
    payload = build_payload(
        {
            "text": summary,
            "chunk_id": f"{document.get('filename')}::summary",
            "filename": document.get("filename"),
            "file_type": document.get("file_type"),
            "source_file": document.get("source_file"),
            "page_number": None,
            "slide_index": None,
            "section_heading": "document_summary",
            "char_start": 0,
            "char_end": len(summary),
        },
        document,
        meta,
    )
    payload["summary_kind"] = "document_summary"
    payload["document_summary"] = summary
    return {
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{document.get('filename')}::summary")),
        "vector": vector,
        "payload": payload,
    }


def ingest_file_stream(path, store, embedder, settings, meta: Optional[dict] = None, summary_store=None):
    """Load, chunk, embed and store a single file, yielding progress events.

    Yields ``{"stage": ...}`` dicts: ``parsing``, ``summarizing`` (when a
    summary store is given), ``chunking``, ``embedding`` (with done/total, once
    per batch), ``storing``, then the terminal ``{"stage": "stored", "chunks": n}``.

    Idempotent: existing points for the same filename are removed first, so
    re-ingesting an updated document never leaves stale chunks behind.
    """
    path = Path(path)
    yield {"stage": "parsing"}
    document = load_file(str(path))

    summary_point = None
    if summary_store is not None:
        yield {"stage": "summarizing"}
        summary_point = build_summary_point(document, embedder, meta)

    yield {"stage": "chunking"}
    chunks = chunk_file(
        document,
        strategy=settings.chunk_strategy,
        chunk_size=settings.chunk_size,
        overlap=settings.chunk_overlap,
        chunk_floor=getattr(settings, "chunk_floor", 0) or 0,
    )
    total = len(chunks)
    if not total:
        yield {"stage": "stored", "chunks": 0}
        return

    texts = [chunk_embed_text(chunk, document) for chunk in chunks]
    vectors: list = []
    yield {"stage": "embedding", "done": 0, "total": total}
    for start in range(0, total, EMBED_BATCH):
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
    if summary_store is not None:
        summary_store.delete_by_filename(document.get("filename") or path.name)
    store.upsert(points)
    if summary_point is not None:
        summary_store.upsert([summary_point])
    yield {"stage": "stored", "chunks": len(points)}


def ingest_file(path, store, embedder, settings, meta: Optional[dict] = None, summary_store=None) -> int:
    """Like :func:`ingest_file_stream`, for callers that only need the count."""
    count = 0
    for event in ingest_file_stream(path, store, embedder, settings, meta, summary_store=summary_store):
        if event.get("stage") == "stored":
            count = event["chunks"]
    return count

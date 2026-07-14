"""The single shared data contract.

Every chunk stored in Qdrant uses exactly these payload fields, and every
consumer (retriever, API services) reads them through the helpers here. This
is what keeps ingestion and retrieval from drifting apart.
"""

# Canonical payload keys for a stored chunk.
PAYLOAD_FIELDS = (
    "text",
    "source_file",
    "filename",
    "file_type",
    "page_number",
    "slide_index",
    "section_heading",
    "chunk_id",
    "char_start",
    "char_end",
    "document_type",
    "department",
    "client_project",
    "tags",
    "tag_paths",
    "description",
    "content_hash",
    "document_summary",
    "summary_kind",
)

# Longest excerpt (characters) sent with a citation before it is truncated.
_EXCERPT_LIMIT = 240


def _excerpt(payload: dict) -> str:
    """A compact, whitespace-collapsed snippet of a chunk for citation cards."""
    text = " ".join((payload.get("text") or "").split())
    if len(text) > _EXCERPT_LIMIT:
        text = text[:_EXCERPT_LIMIT].rstrip() + "..."
    return text


def page_label(payload: dict):
    """Human-facing location of a chunk: page number, else slide index, else 0."""
    return payload.get("page_number") or payload.get("slide_index") or 0


def to_source(payload: dict, score) -> dict:
    """Map a stored payload + similarity score to the citation shape the UI expects."""
    filename = payload.get("filename", "unknown")
    # Human-friendly title is the filename without its extension (matches the
    # concept); the full filename + page sit in the card's meta line.
    title = filename.rsplit(".", 1)[0] if "." in filename else filename
    return {
        "filename": filename,
        "title": title,
        "page": page_label(payload),
        "score": round(score, 4) if score is not None else None,
        "excerpt": _excerpt(payload),
    }

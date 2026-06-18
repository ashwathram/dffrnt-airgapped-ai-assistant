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
)


def page_label(payload: dict):
    """Human-facing location of a chunk: page number, else slide index, else 0."""
    return payload.get("page_number") or payload.get("slide_index") or 0


def to_source(payload: dict, score) -> dict:
    """Map a stored payload + similarity score to the citation shape the UI expects."""
    return {
        "filename": payload.get("filename", "unknown"),
        "page": page_label(payload),
        "score": round(score, 4) if score is not None else None,
    }

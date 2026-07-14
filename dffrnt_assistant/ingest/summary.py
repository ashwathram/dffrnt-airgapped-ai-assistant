"""Document summary helpers used during ingestion-time routing."""

from __future__ import annotations


def build_document_summary_prompt(document: dict, max_chars: int = 6000) -> str:
    """Return a compact prompt that asks the LLM to summarize the document."""
    title = document.get("document_title") or document.get("filename") or "document"
    text = (document.get("text") or "").strip()
    if len(text) > max_chars:
        text = text[:max_chars]
    return (
        "Summarize the uploaded document for retrieval routing.\n"
        "Return 2-4 short sentences, plain text only.\n"
        "Focus on the document type, topic, named entities, and what a user might ask about.\n"
        "Do not invent facts.\n\n"
        f"Document title: {title}\n\n"
        f"Document text:\n{text}\n\n"
        "Summary:"
    )


def generate_document_summary(document: dict, llm, max_chars: int = 6000) -> str:
    """Create a short routing summary for a document.

    If generation fails for any reason, return a conservative fallback excerpt
    so ingestion can continue.
    """
    text = (document.get("text") or "").strip()
    if not text:
        return ""
    prompt = build_document_summary_prompt(document, max_chars=max_chars)
    try:
        summary = llm.generate(prompt).strip()
    except Exception:
        summary = ""
    if summary:
        return summary
    fallback = " ".join(text.split())
    return fallback[:400].rstrip()

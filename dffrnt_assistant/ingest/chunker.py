"""Chunking helpers for fixed-size, sentence, paragraph, and recursive splits."""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Dict, List, Sequence


def _build_chunk(piece: str, start: int, end: int) -> Dict:
    return {
        "id": str(uuid.uuid4()),
        "text": piece,
        "char_start": start,
        "char_end": end,
    }


def chunk_text(text: str, chunk_size: int = 2000, overlap: int = 200) -> List[Dict]:
    """Split `text` into fixed-size overlapping chunks."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0")
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    chunks = []
    start = 0
    text_len = len(text)
    while start < text_len:
        end = start + chunk_size
        piece = text[start:end]
        chunks.append(_build_chunk(piece, start, min(end, text_len)))
        if end >= text_len:
            break
        start = end - overlap

    return chunks


def _regex_segments(text: str, pattern: str) -> List[Dict]:
    segments = []
    for match in re.finditer(pattern, text, flags=re.S):
        piece = match.group(0)
        if piece.strip():
            start, end = match.span()
            segments.append({"text": piece, "char_start": start, "char_end": end})
    return segments


def _pack_segments(
    segments: Sequence[Dict], chunk_size: int, overlap: int, min_chars: int = 0
) -> List[Dict]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0")
    if overlap < 0:
        raise ValueError("overlap must be >= 0")
    if min_chars < 0:
        raise ValueError("min_chars must be >= 0")
    if not segments:
        return []

    chunks: List[Dict] = []
    index = 0
    while index < len(segments):
        start_index = index
        current = [segments[index]]
        index += 1

        while index < len(segments):
            candidate = "".join(item["text"] for item in current + [segments[index]])
            if len(candidate) > chunk_size and len("".join(item["text"] for item in current)) >= max(min_chars, 1):
                break
            current.append(segments[index])
            index += 1

        piece = "".join(item["text"] for item in current)
        chunks.append(_build_chunk(piece, current[0]["char_start"], current[-1]["char_end"]))

        if index >= len(segments):
            break
        index = max(start_index + 1, index - overlap)

    return chunks


def chunk_sentences(text: str, chunk_size: int = 1200, overlap: int = 1) -> List[Dict]:
    """Split text by sentence boundaries and then pack sentences into chunks."""
    sentences = _regex_segments(text, r".+?(?:[.!?]+(?:\s+|$)|$)")
    if not sentences:
        return chunk_text(text, chunk_size=chunk_size, overlap=max(1, min(overlap, chunk_size - 1)))
    return _pack_segments(sentences, chunk_size=chunk_size, overlap=overlap)


def chunk_paragraphs(text: str, chunk_size: int = 1200, overlap: int = 1) -> List[Dict]:
    """Split text by paragraph boundaries and then pack paragraphs into chunks."""
    paragraphs = _regex_segments(text, r".+?(?:\n\s*\n+|$)")
    if not paragraphs:
        return chunk_text(text, chunk_size=chunk_size, overlap=max(1, min(overlap, chunk_size - 1)))
    return _pack_segments(paragraphs, chunk_size=chunk_size, overlap=overlap)


def _split_to_atomic(text: str, chunk_size: int, overlap: int) -> List[Dict]:
    """Break `text` into segments each <= chunk_size, preserving char offsets.

    Splits on paragraphs, then sentences, then fixed size — only going finer when
    a piece is still too large. Returns segments (not packed) for `_pack_segments`.
    """
    atomic: List[Dict] = []
    for paragraph in _regex_segments(text, r".+?(?:\n\s*\n+|$)"):
        base = paragraph["char_start"]
        if len(paragraph["text"]) <= chunk_size:
            atomic.append(paragraph)
            continue
        for sentence in chunk_sentences(paragraph["text"], chunk_size=chunk_size, overlap=1):
            s_start = base + sentence["char_start"]
            if len(sentence["text"]) <= chunk_size:
                atomic.append({"text": sentence["text"], "char_start": s_start,
                               "char_end": s_start + len(sentence["text"])})
                continue
            for fixed in chunk_text(sentence["text"], chunk_size=chunk_size, overlap=overlap):
                f_start = s_start + fixed["char_start"]
                atomic.append({"text": fixed["text"], "char_start": f_start,
                               "char_end": f_start + len(fixed["text"])})
    return atomic


def chunk_recursive(
    text: str, chunk_size: int = 1200, overlap: int = 150, min_chars: int = 0
) -> List[Dict]:
    """Recursively split by paragraph, sentence, then fixed size, packing small
    adjacent segments together up to chunk_size (so prose with many short
    paragraphs does not explode into one chunk per line)."""
    atomic = _split_to_atomic(text, chunk_size, overlap)
    if not atomic:
        return chunk_text(text, chunk_size=chunk_size, overlap=overlap)
    return _pack_segments(atomic, chunk_size=chunk_size, overlap=1, min_chars=min_chars)


def chunk_by_strategy(
    text: str, strategy: str = "recursive", chunk_size: int = 1200, overlap: int = 150, min_chars: int = 0
) -> List[Dict]:
    strategy = strategy.lower().strip()
    if strategy == "fixed":
        return chunk_text(text, chunk_size=chunk_size, overlap=overlap)
    if strategy == "sentence":
        return chunk_sentences(text, chunk_size=chunk_size, overlap=1)
    if strategy == "paragraph":
        return chunk_paragraphs(text, chunk_size=chunk_size, overlap=1)
    if strategy == "recursive":
        return chunk_recursive(text, chunk_size=chunk_size, overlap=overlap, min_chars=min_chars)
    raise ValueError(f"Unsupported chunking strategy: {strategy}")


def chunk_file(
    file_record: dict, strategy: str = "recursive", chunk_size: int = 512, overlap: int = 64, chunk_floor: int = 0
) -> List[Dict]:
    """Chunk a ``Document`` (from ``loaders.load_file``) into metadata-rich chunks.

    Chunk IDs are deterministic (``filename::section::chunk_N``) so re-ingesting
    the same file overwrites the same points instead of duplicating them.
    """
    if not file_record:
        return []

    filename = file_record.get("filename") or Path(file_record.get("source_file", "")).name
    file_type = file_record.get("file_type")
    sections = file_record.get("sections") or [
        {
            "text": file_record.get("text", ""),
            "char_start": 0,
            "char_end": len(file_record.get("text", "")),
            "page_number": None,
            "slide_index": None,
            "section_heading": None,
        }
    ]

    all_chunks: List[Dict] = []
    for section_index, section in enumerate(sections):
        section_text = section.get("text", "")
        heading = section.get("section_heading") or f"section{section_index + 1}"
        section_start = section.get("char_start", 0)

        relative_chunks = chunk_by_strategy(
            section_text, strategy=strategy, chunk_size=chunk_size, overlap=overlap, min_chars=chunk_floor
        )

        for chunk_index, relative in enumerate(relative_chunks, start=1):
            chunk_id = f"{filename}::{heading}::chunk_{chunk_index}"
            all_chunks.append(
                {
                    "chunk_id": chunk_id,
                    "text": relative.get("text"),
                    "char_start": section_start + relative.get("char_start", 0),
                    "char_end": section_start + relative.get("char_end", 0),
                    "source_file": file_record.get("source_file"),
                    "filename": filename,
                    "file_type": file_type,
                    "page_number": section.get("page_number"),
                    "slide_index": section.get("slide_index"),
                    "section_heading": heading,
                }
            )

    if chunk_floor > 0 and len(all_chunks) > 1:
        merged: List[Dict] = []
        buffer = dict(all_chunks[0])
        for nxt in all_chunks[1:]:
            if len(buffer.get("text") or "") < chunk_floor:
                buffer["text"] = f'{buffer.get("text") or ""}\n\n{nxt.get("text") or ""}'.strip()
                buffer["char_end"] = nxt.get("char_end")
                buffer["slide_index"] = buffer.get("slide_index") or nxt.get("slide_index")
                buffer["page_number"] = buffer.get("page_number") or nxt.get("page_number")
                if not buffer.get("section_heading") and nxt.get("section_heading"):
                    buffer["section_heading"] = nxt.get("section_heading")
                continue
            merged.append(buffer)
            buffer = dict(nxt)
        merged.append(buffer)

        renamed: List[Dict] = []
        for chunk_index, chunk in enumerate(merged, start=1):
            updated = dict(chunk)
            updated["chunk_id"] = f"{filename}::merged::chunk_{chunk_index}"
            renamed.append(updated)
        all_chunks = renamed

    return all_chunks

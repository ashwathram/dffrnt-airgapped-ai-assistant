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


def _pack_segments(segments: Sequence[Dict], chunk_size: int, overlap: int) -> List[Dict]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0")
    if overlap < 0:
        raise ValueError("overlap must be >= 0")
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
            if len(candidate) > chunk_size and current:
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


def chunk_recursive(text: str, chunk_size: int = 1200, overlap: int = 150) -> List[Dict]:
    """Recursively split by paragraph, sentence, and finally fixed-size chunks."""
    chunks: List[Dict] = []
    paragraphs = _regex_segments(text, r".+?(?:\n\s*\n+|$)")
    if not paragraphs:
        return chunk_text(text, chunk_size=chunk_size, overlap=overlap)

    for paragraph in paragraphs:
        piece = paragraph["text"]
        if len(piece) <= chunk_size:
            chunks.append(_build_chunk(piece, paragraph["char_start"], paragraph["char_end"]))
            continue

        sentence_chunks = chunk_sentences(piece, chunk_size=chunk_size, overlap=1)
        if sentence_chunks and len(sentence_chunks) > 1:
            for sentence_chunk in sentence_chunks:
                if len(sentence_chunk["text"]) <= chunk_size:
                    chunks.append(
                        _build_chunk(
                            sentence_chunk["text"],
                            paragraph["char_start"] + sentence_chunk["char_start"],
                            paragraph["char_start"] + sentence_chunk["char_end"],
                        )
                    )
                else:
                    fixed_chunks = chunk_text(
                        sentence_chunk["text"], chunk_size=chunk_size, overlap=overlap
                    )
                    for fixed_chunk in fixed_chunks:
                        chunks.append(
                            _build_chunk(
                                fixed_chunk["text"],
                                paragraph["char_start"]
                                + sentence_chunk["char_start"]
                                + fixed_chunk["char_start"],
                                paragraph["char_start"]
                                + sentence_chunk["char_start"]
                                + fixed_chunk["char_end"],
                            )
                        )
            continue

        fixed_chunks = chunk_text(piece, chunk_size=chunk_size, overlap=overlap)
        for fixed_chunk in fixed_chunks:
            chunks.append(
                _build_chunk(
                    fixed_chunk["text"],
                    paragraph["char_start"] + fixed_chunk["char_start"],
                    paragraph["char_start"] + fixed_chunk["char_end"],
                )
            )

    return chunks


def chunk_by_strategy(
    text: str, strategy: str = "fixed", chunk_size: int = 1200, overlap: int = 150
) -> List[Dict]:
    strategy = strategy.lower().strip()
    if strategy == "fixed":
        return chunk_text(text, chunk_size=chunk_size, overlap=overlap)
    if strategy == "sentence":
        return chunk_sentences(text, chunk_size=chunk_size, overlap=1)
    if strategy == "paragraph":
        return chunk_paragraphs(text, chunk_size=chunk_size, overlap=1)
    if strategy == "recursive":
        return chunk_recursive(text, chunk_size=chunk_size, overlap=overlap)
    if strategy == "semantic":
        # placeholder: semantic packing can be implemented with embeddings later
        return chunk_recursive(text, chunk_size=chunk_size, overlap=overlap)
    raise ValueError(f"Unsupported chunking strategy: {strategy}")


def list_chunking_strategies() -> List[str]:
    return ["fixed", "sentence", "paragraph", "recursive", "semantic"]


def chunk_file(
    file_record: dict, strategy: str = "recursive", chunk_size: int = 1000, overlap: int = 150
) -> List[Dict]:
    """Chunk a file into metadata-rich chunks with deterministic IDs.

    The input should look like the dict returned by `load_file`.
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
    for sidx, section in enumerate(sections):
        sec_text = section.get("text", "")
        sec_heading = section.get("section_heading") or f"section{sidx + 1}"
        sec_page = section.get("page_number")
        sec_slide = section.get("slide_index")
        sec_start = section.get("char_start", 0)

        # chunk the section text using existing strategies (returns relative char offsets)
        relative_chunks = chunk_by_strategy(
            sec_text, strategy=strategy, chunk_size=chunk_size, overlap=overlap
        )

        for idx, rc in enumerate(relative_chunks, start=1):
            # rc char offsets are relative to section; convert to absolute
            abs_start = sec_start + rc.get("char_start", 0)
            abs_end = sec_start + rc.get("char_end", len(rc.get("text", "")))
            chunk_id = f"{filename}::{sec_heading}::chunk_{idx}"
            chunk = {
                "chunk_id": chunk_id,
                "id": chunk_id,
                "text": rc.get("text"),
                "char_start": abs_start,
                "char_end": abs_end,
                "source_file": file_record.get("source_file"),
                "filename": filename,
                "file_type": file_type,
                "page_number": sec_page,
                "slide_index": sec_slide,
                "section_heading": sec_heading,
            }
            all_chunks.append(chunk)

    return all_chunks

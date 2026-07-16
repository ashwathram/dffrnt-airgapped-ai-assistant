"""Chunk-shape health on the evaluation corpus. Pure offline (no services):
loads each corpus file with the production loaders and chunker at the default
settings and asserts the chunks are usable for retrieval.
"""

import pytest

from dffrnt_assistant.config import Settings
from dffrnt_assistant.ingest.chunker import chunk_file
from dffrnt_assistant.ingest.loaders import load_file

from .corpus_gen import CORPUS_DIR, UPLOADS

CORPUS_FILES = sorted(CORPUS_DIR / name for name in UPLOADS)


def _chunks(path, chunk_floor):
    settings = Settings()
    document = load_file(str(path))
    return chunk_file(
        document,
        strategy=settings.chunk_strategy,
        chunk_size=settings.chunk_size,
        overlap=settings.chunk_overlap,
        chunk_floor=chunk_floor,
    )


@pytest.mark.parametrize("path", CORPUS_FILES, ids=lambda p: p.name)
def test_corpus_file_chunks_cleanly(path):
    chunks = _chunks(path, Settings().chunk_floor)
    assert chunks, "document produced no chunks"
    # The chunk floor merges tiny fragments forward, so at most the final chunk
    # of a document may be shorter than the floor.
    tiny = [c for c in chunks if len(c["text"]) < Settings().chunk_floor]
    assert len(tiny) <= 1, f"{len(tiny)} sub-floor chunks survived the merge"
    assert all(c["chunk_id"] and c["text"].strip() for c in chunks)


def test_chunk_floor_reduces_fragmentation():
    def tiny_fraction(chunk_floor):
        lengths = [
            len(c["text"]) for p in CORPUS_FILES for c in _chunks(p, chunk_floor)
        ]
        return sum(1 for n in lengths if n < 100) / len(lengths)

    assert tiny_fraction(Settings().chunk_floor) <= tiny_fraction(0)

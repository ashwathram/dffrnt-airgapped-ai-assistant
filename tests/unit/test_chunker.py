import pytest

from dffrnt_assistant.ingest.chunker import chunk_by_strategy, chunk_file, chunk_text


def test_chunk_text_respects_size_and_covers_text():
    text = "abcdefghij" * 10  # 100 chars
    chunks = chunk_text(text, chunk_size=30, overlap=5)
    assert all(len(c["text"]) <= 30 for c in chunks)
    assert chunks[0]["char_start"] == 0
    assert chunks[-1]["char_end"] == len(text)


def test_chunk_text_validation():
    with pytest.raises(ValueError):
        chunk_text("x", chunk_size=0)
    with pytest.raises(ValueError):
        chunk_text("x", chunk_size=10, overlap=10)


def test_unknown_strategy_raises():
    with pytest.raises(ValueError):
        chunk_by_strategy("hello", strategy="bogus")


def test_chunk_file_has_deterministic_ids_and_metadata():
    document = {
        "filename": "a.txt",
        "file_type": "txt",
        "source_file": "/docs/a.txt",
        "sections": [
            {
                "text": "Para one is short.\n\nPara two has a bit more text in it.",
                "char_start": 0,
                "section_heading": None,
                "page_number": 1,
                "slide_index": None,
            }
        ],
    }
    chunks = chunk_file(document, strategy="recursive", chunk_size=40, overlap=8)
    assert chunks
    assert chunks[0]["chunk_id"].startswith("a.txt::")
    assert chunks[0]["page_number"] == 1
    assert chunks[0]["filename"] == "a.txt"

    again = chunk_file(document, strategy="recursive", chunk_size=40, overlap=8)
    assert [c["chunk_id"] for c in chunks] == [c["chunk_id"] for c in again]

"""Backfill CLI core logic with fakes (no Qdrant / Ollama)."""

from pathlib import Path

from dffrnt_assistant.ingest.backfill import (
    _document_from_chunks,
    backfill_summaries,
    missing_summaries,
)


class FakeStore:
    def __init__(self, payloads):
        self.payloads = payloads
        self.upserted = []

    def all_payloads(self, limit=10000):
        return list(self.payloads)

    def payloads_by_filenames(self, filenames, limit=0):
        wanted = set(filenames)
        return [p for p in self.payloads if p.get("filename") in wanted]

    def upsert(self, points):
        self.upserted.extend(points)


class FakeLLMEmbedder:
    def generate(self, prompt):
        return "A concise summary."

    def embed_documents(self, texts):
        return [[0.0] * 8 for _ in texts]


def _chunk(filename, text, char_start=0, **extra):
    return {"filename": filename, "text": text, "char_start": char_start, **extra}


def test_missing_summaries_diffs_the_collections():
    store = FakeStore([_chunk("a.txt", "x"), _chunk("b.txt", "y")])
    summary_store = FakeStore([{"filename": "a.txt"}])
    assert missing_summaries(store, summary_store) == ["b.txt"]


def test_document_from_chunks_orders_by_offset():
    doc = _document_from_chunks(
        "a.txt",
        [_chunk("a.txt", "second", 50, file_type="txt"), _chunk("a.txt", "first", 0)],
    )
    assert doc["text"] == "second\n\nfirst" or doc["text"] == "first\n\nsecond"
    # sorted by char_start -> "first" leads
    assert doc["text"].startswith("first")
    assert doc["filename"] == "a.txt"


def test_backfill_generates_summary_from_chunks_with_meta(tmp_path):
    store = FakeStore(
        [_chunk("gone.txt", "Body text of a vanished file.", 0,
                file_type="txt", tags=["HR"], description="desc", content_hash="h")]
    )
    summary_store = FakeStore([])
    n = backfill_summaries(store, summary_store, FakeLLMEmbedder(), tmp_path)
    assert n == 1
    point = summary_store.upserted[0]
    assert point["payload"]["document_summary"] == "A concise summary."
    assert point["payload"]["filename"] == "gone.txt"
    assert point["payload"]["tags"] == ["HR"]          # meta carried onto the summary
    assert point["payload"]["description"] == "desc"


def test_backfill_dry_run_writes_nothing(tmp_path):
    store = FakeStore([_chunk("gone.txt", "Body.", 0)])
    summary_store = FakeStore([])
    n = backfill_summaries(store, summary_store, FakeLLMEmbedder(), tmp_path, dry_run=True)
    assert n == 1
    assert summary_store.upserted == []


def test_backfill_skips_docs_with_no_text(tmp_path):
    store = FakeStore([_chunk("empty.txt", "", 0)])
    summary_store = FakeStore([])
    n = backfill_summaries(store, summary_store, FakeLLMEmbedder(), tmp_path)
    assert n == 0
    assert summary_store.upserted == []

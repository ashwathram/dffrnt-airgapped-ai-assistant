"""Backfill CLI core logic with fakes (no Qdrant / Ollama)."""

from pathlib import Path

from dffrnt_assistant.ingest import backfill
from dffrnt_assistant.ingest.backfill import (
    _document_from_chunks,
    backfill_summaries,
    ingest_missing_files,
    missing_summaries,
    orphaned_documents,
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

    def has_document(self, filename):
        return any(p.get("filename") == filename for p in self.payloads)

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


def test_ingest_missing_skips_present_docs_without_force(tmp_path, monkeypatch):
    (tmp_path / "present.txt").write_text("hi")
    store = FakeStore([_chunk("present.txt", "hi", 0)])
    calls = []
    monkeypatch.setattr(backfill, "ingest_file", lambda *a, **k: calls.append(k) or 1)
    n = ingest_missing_files(store, FakeLLMEmbedder(), None, tmp_path)
    assert n == 0 and calls == []          # already ingested -> skipped


def test_ingest_force_reingests_present_and_preserves_meta(tmp_path, monkeypatch):
    (tmp_path / "present.txt").write_text("fresh bytes on disk")
    store = FakeStore([
        _chunk("present.txt", "old body", 0, tags=["HR"], tag_paths=["HR/x"],
               description="desc", content_hash="stale"),
    ])
    captured = {}

    def fake_ingest(path, s, emb, settings, meta=None, summary_store=None):
        captured["meta"] = meta
        return 3

    monkeypatch.setattr(backfill, "ingest_file", fake_ingest)
    n = ingest_missing_files(store, FakeLLMEmbedder(), None, tmp_path, force=True)
    assert n == 1
    assert captured["meta"]["tags"] == ["HR"]           # curation metadata carried over
    assert captured["meta"]["description"] == "desc"
    assert captured["meta"]["content_hash"] != "stale"  # recomputed from disk


def test_orphaned_documents_flags_docs_without_source_files(tmp_path):
    (tmp_path / "ondisk.txt").write_text("present")
    store = FakeStore([_chunk("ondisk.txt", "a", 0), _chunk("gone.pdf", "b", 0)])
    # gone.pdf is in the collection but has no file in data_dir -> orphan.
    assert orphaned_documents(store, tmp_path) == ["gone.pdf"]

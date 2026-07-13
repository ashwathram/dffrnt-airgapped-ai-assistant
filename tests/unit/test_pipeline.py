"""Exercises the unified ingestion wiring without Qdrant or Ollama, using fakes."""

from dffrnt_assistant.config import Settings
from dffrnt_assistant.ingest.pipeline import build_payload, ingest_file


class FakeEmbedder:
    def embed_texts(self, texts):
        return [[0.0] * 8 for _ in texts]

    def embed_documents(self, texts):
        return self.embed_texts(texts)


class FakeStore:
    def __init__(self):
        self.deleted = []
        self.points = []

    def delete_by_filename(self, filename):
        self.deleted.append(filename)

    def upsert(self, points):
        self.points = points


def test_build_payload_applies_metadata():
    chunk = {
        "text": "t",
        "chunk_id": "f.txt::s::chunk_1",
        "filename": "f.txt",
        "file_type": "txt",
        "source_file": "/f.txt",
        "page_number": 1,
        "slide_index": None,
        "section_heading": "s",
        "char_start": 0,
        "char_end": 1,
    }
    document = {"filename": "f.txt", "file_type": "txt", "source_file": "/f.txt"}
    payload = build_payload(chunk, document, {"tags": ["x"], "department": "R&D"})
    assert payload["tags"] == ["x"]
    assert payload["department"] == "R&D"
    assert payload["text"] == "t"
    assert payload["page_number"] == 1
    assert payload["summary_kind"] == "chunk"
    assert payload["document_summary"] == ""


def test_ingest_file_deletes_then_upserts(tmp_path):
    path = tmp_path / "doc.txt"
    path.write_text("Alpha paragraph.\n\nBeta paragraph has several more words in it.")

    settings = Settings()
    settings.chunk_size = 40
    settings.chunk_overlap = 8

    store = FakeStore()
    count = ingest_file(path, store, FakeEmbedder(), settings)

    assert count > 0
    assert store.deleted == ["doc.txt"]  # idempotent: stale chunks removed first
    assert len(store.points) == count
    assert all({"id", "vector", "payload"} <= set(p) for p in store.points)
    assert store.points[0]["payload"]["filename"] == "doc.txt"

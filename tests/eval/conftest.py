"""Fixtures for the evaluation suite: production-shaped wiring against the live
Qdrant + Ollama stack, with an opt-in ``--reset-corpus`` that re-ingests the
synthetic corpus (destructive: wipes the document and summary collections)."""

import hashlib
import urllib.request
from types import SimpleNamespace

import pytest

from dffrnt_assistant.config import load_settings
from dffrnt_assistant.ingest.pipeline import ingest_file
from dffrnt_assistant.ingest.tags import normalize_tag_payload
from dffrnt_assistant.ollama import OllamaClient
from dffrnt_assistant.rag import RagPipeline
from dffrnt_assistant.retrieval.retriever import Retriever
from dffrnt_assistant.retrieval.store import VectorStore

from .corpus_gen import CORPUS_DIR, UPLOADS


def _reachable(url: str) -> bool:
    try:
        urllib.request.urlopen(url, timeout=3)
        return True
    except Exception:
        return False


def _reset_corpus(settings, store, summary_store, llm) -> None:
    store.recreate_collection()
    summary_store.recreate_collection()
    for filename, (tags, description) in UPLOADS.items():
        path = CORPUS_DIR / filename
        leaf_tags, tag_paths = normalize_tag_payload(tags.split(","))
        meta = {
            "tags": leaf_tags,
            "tag_paths": tag_paths,
            "description": description,
            "content_hash": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        chunks = ingest_file(path, store, llm, settings, meta, summary_store=summary_store)
        print(f"  ingested {filename}: {chunks} chunks")


@pytest.fixture(scope="session")
def settings():
    return load_settings()


@pytest.fixture(scope="session")
def stack(settings, request):
    """The live stores + LLM client, wired the way api/app.py wires them.

    Skips the whole suite when Qdrant/Ollama are unreachable, and when the
    evaluation corpus is not in the knowledge base (unless ``--reset-corpus``).
    """
    if not _reachable(settings.qdrant_url + "/healthz"):
        pytest.skip(f"Qdrant not reachable at {settings.qdrant_url} — run deploy/start.sh")
    if not _reachable(settings.ollama_url):
        pytest.skip(f"Ollama not reachable at {settings.ollama_url} — run deploy/start.sh")

    store = VectorStore(
        settings.qdrant_url, settings.collection_name, settings.vector_size, settings.distance
    )
    summary_store = VectorStore(
        settings.qdrant_url, settings.summary_collection_name,
        settings.vector_size, settings.distance,
    )
    llm = OllamaClient(
        settings.ollama_url, settings.llm_model, settings.embed_model,
        settings.llm_temperature, settings.llm_timeout,
        settings.embed_query_prefix, settings.embed_document_prefix,
        settings.llm_num_ctx, settings.llm_top_p, settings.llm_top_k,
        settings.llm_repeat_penalty, settings.llm_num_predict,
    )
    store.ensure_collection()
    summary_store.ensure_collection()

    if request.config.getoption("--reset-corpus"):
        _reset_corpus(settings, store, summary_store, llm)
    missing = [f for f in UPLOADS if not store.has_document(f)]
    if missing:
        pytest.skip(f"corpus not ingested ({len(missing)} docs missing) — rerun with --reset-corpus")

    return SimpleNamespace(store=store, summary_store=summary_store, llm=llm)


@pytest.fixture(scope="session")
def retriever(stack, settings):
    """The production retriever (document-summary routing + aggregate grouping)."""
    return Retriever(stack.store, stack.llm, settings, summary_store=stack.summary_store)


@pytest.fixture(scope="session")
def plain_retriever(stack, settings):
    """Plain chunk search only — the baseline the production signals must beat."""
    return Retriever(stack.store, stack.llm, settings)


@pytest.fixture(scope="session")
def pipeline(retriever, stack, settings):
    return RagPipeline(retriever, stack.llm, settings)

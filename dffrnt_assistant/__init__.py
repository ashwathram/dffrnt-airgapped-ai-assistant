"""DFFRNT air-gapped RAG assistant.

A single, loosely-coupled pipeline:

    ingest  -> loaders -> chunker -> embed (Ollama) -> vector store (Qdrant)
    query   -> embed (Ollama) -> retrieve -> assemble context -> generate (Ollama)

Every tunable lives in :mod:`dffrnt_assistant.config`.
"""

__version__ = "0.1.0"

"""DFFRNT air-gapped RAG assistant.

    ingest  -> loaders -> chunker -> embed (Ollama) -> vector store (Qdrant)
    query   -> embed -> retrieve -> assemble context -> generate (Ollama)

Every tunable lives in :mod:`dffrnt_assistant.config`.
"""

__version__ = "0.1.0"

# Architecture Overview

This document maps the high-level architecture described in the pitch to concrete code locations in the repository.

High-level components

- Ingestion Pipeline: converts documents into text, chunks them, embeds them, and upserts into a vector store.
  - `src/ingestion/loaders.py` — file readers (PDF/DOCX/PPTX/CSV)
  - `src/processing/chunker.py` — chunking logic
  - `src/embeddings/embedder.py` — embeddings wrapper
  - `src/vector_store/qdrant_store.py` — Qdrant wrapper

- Local LLM + RAG
  - RAG orchestration will combine query embedding -> vector search -> prompt assembly -> local LLM
  - Local LLM runners (examples): Ollama, or a small local LLM run via LangChain connectors (implementation TBD)

- UI / Interaction
  - Minimal UI prototypes can be placed in `app/` or a `streamlit_app.py` in root
  - The assistant should provide source attribution and allow follow-up clarifications

- Specialized tools
  - Resume generator, RFP templater, and content drafter are higher-level agents that call the RAG stack

Data and models
- `database/raw/` — raw input files (kept in the repo for demo material)
- `models/` — store model artifacts for local use (not committed when large)

Deployment notes
- Air-gapped deployment requires copying wheels and model files into the host and disabling external downloads.
- Qdrant can be run locally (Docker) — helper command in `src/vector_store/qdrant_store.py`.

Next steps to complete RAG flow
1. Implement query runner that uses `Embedder` -> `QdrantStore.search` -> prompt builder -> LLM runner. 
2. Add a minimal Streamlit UI to query and display results with sources.
3. Add provenance metadata to chunk payloads during upsert.
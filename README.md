# Air-Gapped Private AI Knowledge and Content Assistant for DFFRNT

**A secure, fully offline AI system for DFFRNT** — built with open-source models and Retrieval-Augmented Generation (RAG).

![Status](https://img.shields.io/badge/Status-Active-brightgreen)
![License](https://img.shields.io/badge/License-MIT-blue)

## Overview

This project delivers a **private, air-gapped AI assistant** that serves as DFFRNT's internal "central brain". It ingests and organizes confidential company knowledge (projects, proposals, timesheets, resumes, etc.) and answers internal queries with grounded, source-attributed responses.

The system runs **completely offline** on dedicated hardware. Embeddings and text generation are served by a local **Ollama** instance; vectors are stored in a local **Qdrant** instance. No data leaves the machine.

---

## Key Features

- Fully air-gapped deployment (no internet required after setup)
- Retrieval-Augmented Generation (RAG) for accurate, source-grounded answers
- Single conversational web UI with a document library and upload flow
- Document ingestion for **PDF, DOCX, PPTX, XLSX, CSV, TXT, Markdown**
- One ingestion pipeline shared by the web upload and the batch CLI
- Source attribution and prompt-injection-resistant system prompt
- Standard-library-only LLM client (no heavy ML frameworks to ship)

---

## Architecture

A single pipeline, with one dedicated module per responsibility:

```
Documents ──▶ ingest (loaders ▶ chunker ▶ embed) ──▶ Qdrant (vectors + metadata)
                                                          ▲
Question ──▶ retrieve (embed ▶ search ▶ assemble) ──▶ RAG (prompt ▶ generate) ──▶ Answer + sources
```

| Area | Module |
|------|--------|
| Configuration (all tunables) | [config.py](dffrnt_assistant/config.py) |
| Shared payload contract | [schema.py](dffrnt_assistant/schema.py) |
| LLM management (Ollama, stdlib only) | [ollama.py](dffrnt_assistant/ollama.py) |
| Document ingestion | [ingest/](dffrnt_assistant/ingest/) (`loaders`, `chunker`, `tags`, `metadata`, `pipeline`) |
| Retrieval & query assembly | [retrieval/](dffrnt_assistant/retrieval/) (`store`, `retriever`) |
| RAG | [rag/](dffrnt_assistant/rag/) (`prompt`, `pipeline`) |
| Presentation (HTTP + UI) | [api/](dffrnt_assistant/api/) (`app`, `services`, `audit`) + [ui/index.html](dffrnt_assistant/ui/index.html) |
| Batch ingestion CLI | [cli.py](dffrnt_assistant/cli.py) |

---

## Configuration

Every tunable (hosts/ports, models, `top_k`, chunk size/overlap, distance metric, collection name, etc.) lives in one place. Set values via a `config.toml` file or environment variables — env wins over the file, which wins over built-in defaults.

```bash
cp config.toml.example config.toml   # then edit
# or, per-run:
API_PORT=9000 TOP_K=8 dffrnt-api
```

See [config.toml.example](config.toml.example) for the full list.

---

## Running locally

Requires a local Qdrant and Ollama (the VSCode task `Setup: All prerequisites` starts both via Docker and pulls the models).

```bash
uv sync                       # installs the package + dependencies
dffrnt-api                    # serve the API + UI at http://localhost:8000
dffrnt-ingest --source-root database/raw   # batch-ingest a folder
```

Both entrypoints read the same configuration and write to the same Qdrant collection.

---

## Tests

```bash
uv run pytest                 # fast unit tests (no services needed)
uv run pytest -m integration  # end-to-end; needs a running server + Qdrant + Ollama
```

---

## Offline deployment

Build a bundle (wheels + container images + models) on a networked machine, transfer the tarball, and install on the air-gapped target. See [deploy/README.md](deploy/README.md).

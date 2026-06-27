# Air-Gapped Private AI Knowledge and Content Assistant for DFFRNT

**A secure, fully offline AI system for DFFRNT** — built with open-source models and Retrieval-Augmented Generation (RAG).

![Status](https://img.shields.io/badge/Status-Active-brightgreen)
![License](https://img.shields.io/badge/License-MIT-blue)

## Overview

This project delivers a **private, air-gapped AI assistant** that serves as DFFRNT's internal "central brain". It ingests and organizes confidential company knowledge (projects, proposals, timesheets, resumes, etc.) and answers internal queries with grounded, source-attributed responses.

The system runs **completely offline** on dedicated hardware. Embeddings and text generation are served by a local **Ollama** instance; vectors are stored in a local **Qdrant** instance. No data leaves the machine.

**Models** (served locally by Ollama):

- **Embeddings:** `bge-m3` — 1024-dimensional vectors, cosine similarity (no task prefixes).
- **LLM:** the `qwen3` family — `qwen3:4b` (lightweight, the offline-bundle default) or `qwen3:30b-a3b` (high-capacity MoE, used in development). The model is set by `llm_model` in `config.toml`; nothing else needs to change.

---

## Key Features

- Fully air-gapped deployment (no internet required after setup)
- Retrieval-Augmented Generation (RAG) for accurate, source-grounded answers
- Single conversational web UI: streaming answers, an optional reasoning trace, a document library, and an upload flow
- Inline **`[n]` citations** that are clickable — clicking one scrolls to and highlights the cited source; cited sources are listed first, with retrieved-but-unused ones collapsed into a dimmed group below
- Tag-based **scoping** to focus retrieval on a chosen subset of documents, plus saved conversations
- Document ingestion for **PDF, DOCX, PPTX, XLSX, CSV, TXT, Markdown** through the web UI's upload flow (single files or whole folders)
- Source attribution and a prompt-injection-resistant system prompt that refuses when the documents don't support an answer
- Generation tuned for RAG: an explicit `num_ctx` so long prompts are never silently truncated, plus a relevance cut (`score_margin`) that drops weak chunks before they reach the prompt
- A reproducible **evaluation harness** ([eval/](eval/)) for tuning retrieval and scoring answer quality
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
| Document ingestion | [ingest/](dffrnt_assistant/ingest/) (`loaders`, `chunker`, `tags`, `pipeline`) |
| Retrieval & query assembly | [retrieval/](dffrnt_assistant/retrieval/) (`store`, `retriever`, `conversation_store`, `tag_store`) |
| RAG | [rag/](dffrnt_assistant/rag/) (`prompt`, `pipeline`) |
| Presentation (HTTP + UI) | [api/](dffrnt_assistant/api/) (`app`, `services`, `audit`) + [ui/](dffrnt_assistant/ui/) (`index.html` + `js/`, `styles/`) |
| Evaluation harness | [eval/](eval/) (`rag_eval`, `answer_eval`, `prompt_size`, `sample_queries`) |

---

## Configuration

Every tunable lives in one place — [config.py](dffrnt_assistant/config.py) defines the schema and defaults. Set values via a `config.toml` file or environment variables — env wins over the file, which wins over built-in defaults.

Notable groups:

- **Models:** `llm_model`, `embed_model`, `vector_size` (must match the embedding model's output dimension).
- **Generation:** `llm_temperature`, and the Ollama options `llm_num_ctx` (context window — set above Ollama's 4096 default so retrieved documents + history aren't truncated), `llm_top_p`, `llm_top_k`, `llm_repeat_penalty`, `llm_num_predict`.
- **Retrieval:** `top_k`, `score_margin` (relative cut: drop hits scoring this far below the best hit), `distance`, chunk size/overlap/strategy.

```bash
cp config.toml.example config.toml   # then edit
# or, per-run:
API_PORT=9000 TOP_K=8 dffrnt-api
```

See [config.toml.example](config.toml.example) for the full list. Retrieval and generation defaults were tuned with the evaluation harness (below).

---

## Running

There are two ways to run, sharing one config (env > `config.toml` > defaults) and the same Qdrant + Ollama containers.

### Development (host API)

The API + UI run on the host (with the debugger / hot reload) against Qdrant and Ollama in Docker. The VSCode task `Setup: All prerequisites` starts both containers and pulls the models; the `DFFRNT AI Assistant (Dev: host API)` launch config then serves everything at http://localhost:8000.

```bash
uv sync                            # installs the package + dependencies
bash deploy/start.sh               # Qdrant + Ollama only
dffrnt-api                         # serve the API + UI at http://localhost:8000
```

### Production (Docker)

The API + UI ship as their own image (built with uv, see [deploy/Dockerfile](deploy/Dockerfile)) and run alongside Qdrant and Ollama via the compose `prod` profile. `run.sh` is the canonical runner. The VSCode task `Run production stack (Docker)` (or launch config `DFFRNT AI Assistant (Prod: Docker container)`) does the whole thing; by hand:

```bash
docker build -t dffrnt-assistant:latest -f deploy/Dockerfile .
bash deploy/run.sh start           # Qdrant + Ollama + API at http://localhost:8000
```

Add documents through the UI's upload flow (single files or whole folders).

---

## Tests

```bash
uv run pytest                 # fast unit tests (no services needed)
uv run pytest -m integration  # end-to-end; needs a running server + Qdrant + Ollama
```

---

## Evaluation

A reproducible harness ([eval/](eval/)) measures retrieval and answer quality against sample queries grounded in the ingested corpus. It runs against the live Qdrant + Ollama stack.

```bash
python -m eval.rag_eval        # sweep top_k / score_margin; reports P@1, recall, kept-chunk counts
python -m eval.prompt_size     # estimate RAG prompt token sizes (to size num_ctx)
python -m eval.answer_eval     # score generated answers: correctness, citation, refusal accuracy
python -m eval.answer_eval --temps 0.1,0.7   # compare generation settings on the same queries
```

`answer_eval` includes out-of-corpus negative controls that the assistant must refuse, directly testing the anti-hallucination guard. Sample queries and their grounded checks live in [eval/sample_queries.py](eval/sample_queries.py).

---

## Deployment

Package the app on a networked machine into **three files** — a tarball, a single
`install.sh`, and a `README.md` — transfer them to the target, and install. The app
ships as a Docker image, so the target needs only Docker (Engine + Compose v2) — no
Python, uv or pip. Two build flavours:

- **OFFLINE** — for an air-gapped box; the bundle carries every image and the Ollama
  model store, so installing needs no internet.
- **AWS** (online) — ships only the app image and pulls the base images + models at
  deploy time, keeping the tarball small.

```bash
# build (networked machine matching the target OS/arch)
deploy/package.sh ~/.ollama/models OFFLINE   # or: deploy/package.sh TARGET_SYSTEM=AWS
# -> dist/{dffrnt-<offline|aws>.tar.gz, install.sh, README.md}

# install + run (target)
./install.sh                                  # checks prereqs, unpacks, starts the stack
cd dffrnt && ./run.sh status                  # manage with start|stop|restart|status|logs
```

See [deploy/README.md](deploy/README.md) for the full build/deploy guide.

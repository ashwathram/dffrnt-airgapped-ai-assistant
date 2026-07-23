# DFFRNT Air-Gapped AI Assistant

A private, fully offline RAG assistant for DFFRNT's internal knowledge. It
ingests company documents (proposals, resumes, policies, spreadsheets, …) and
answers questions with grounded, citation-backed responses. Everything runs
locally: **Ollama** serves the LLM (`qwen3` family) and embeddings (`bge-m3`),
**Qdrant** stores the vectors. No data leaves the machine.

## Features

- Fully air-gapped: no internet required after setup, stdlib-only LLM client
- Conversational web UI with streaming answers, an optional reasoning trace,
  clickable inline `[n]` citations, saved conversations, and answer export
  (TXT / MD / PDF)
- Document library with upload (files or folders), duplicate detection,
  tag taxonomy, and tag-scoped retrieval
- Ingestion for PDF, DOCX, PPTX, XLSX, CSV, TXT, and Markdown
- A prompt-injection-resistant system prompt that refuses when the documents
  don't support an answer

## Architecture

```
Documents ──▶ ingest (loaders ▶ chunker ▶ embed) ──▶ Qdrant (vectors + metadata)
                                                          ▲
Question ──▶ retrieve (embed ▶ search ▶ assemble) ──▶ RAG (prompt ▶ generate) ──▶ Answer + sources
```

| Area | Module |
|------|--------|
| Configuration (all tunables) | [config.py](dffrnt_assistant/config.py) |
| Shared payload contract | [schema.py](dffrnt_assistant/schema.py) |
| Ollama client (LLM + embeddings, stdlib only) | [ollama.py](dffrnt_assistant/ollama.py) |
| Ingestion | [ingest/](dffrnt_assistant/ingest/) — `loaders`, `chunker`, `tags`, `pipeline`, `backfill` CLI |
| Retrieval | [retrieval/](dffrnt_assistant/retrieval/) — `store` (vectors), `retriever`, `doc_store` (tags + conversations) |
| RAG pipeline + prompts | [rag.py](dffrnt_assistant/rag.py) |
| HTTP API + services | [api/](dffrnt_assistant/api/) — `app`, `services`, `export`, `audit` |
| Web UI | [ui/](dffrnt_assistant/ui/) — `index.html` + ES modules in `js/`, styles in `styles/` |

## Configuration

[config.py](dffrnt_assistant/config.py) defines every tunable and its default.
Values come from `config.toml` and environment variables; env beats file beats
defaults.

```bash
cp config.toml.example config.toml   # then edit
# or per-run:
API_PORT=9000 TOP_K=8 dffrnt-api
```

Highlights: `llm_model` / `embed_model` / `vector_size` (must match the embed
model's dimension), `llm_num_ctx` (kept above Ollama's 4096 default so RAG
prompts are never silently truncated), `top_k` + `score_margin` (relevance
cut), and chunking strategy/size/overlap/floor.

## Running

**Development** (host API against containerized Qdrant + Ollama):

```bash
uv sync
uv run python -m installer dev   # Qdrant + Ollama, health-waited, models ensured
dffrnt-api                       # API + UI at http://localhost:8000
```

Or use the VSCode launch config `DFFRNT AI Assistant (Dev: host API)`.

**Production** (everything in Docker):

```bash
docker build -t dffrnt-assistant:latest -f deploy/Dockerfile .
uv run python -m installer start
```

`python -m installer` with no arguments serves the browser control panel
(install/manage/models/logs — rendered by your browser, styled like the app)
and opens it; every operation is also a headless CLI command
(`start`, `stop`, `status`, `logs`, `models`, ... — see `installer/cli.py`).

## Tests

Three suites, all pytest:

```bash
uv run pytest                        # unit + offline chunk-health tests (CI runs these)
uv run pytest -m eval                # retrieval + answer quality; needs Qdrant + Ollama up
uv run pytest -m eval --reset-corpus # …first wiping the KB and re-ingesting tests/eval/corpus
uv run pytest -m integration         # smoke tests against a running API server
```

The evaluation suite ([tests/eval/](tests/eval/)) checks retrieval precision/
recall, answer correctness and citation coverage, and refusal of out-of-scope
questions, against a synthetic ground-truth corpus
([corpus_gen.py](tests/eval/corpus_gen.py)). VSCode launch configs `Tests: …`
run each suite. Answer-quality tests generate with the local LLM, so a full
pass takes a while.

## Deployment

`deploy/package.sh` builds a three-file bundle (tarball + the frozen
`dffrnt-manager` install/manage binary + `README.md`) for either an air-gapped
target (**OFFLINE**: images and models included) or an online one (**AWS**:
pulls at deploy time). The target needs only Docker. See
[deploy/README.md](deploy/README.md).

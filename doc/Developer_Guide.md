# DFFRNT AI Assistant — Developer Guide

This guide is for developers — in particular future grad-student teams —
picking up the DFFRNT Air-Gapped AI Assistant to extend its capabilities. It
assumes general software-engineering background but **zero familiarity with
this codebase**. Read it top to bottom once; afterwards the per-module
docstrings and the two companion documents (Installer Guide, User Guide) fill
in the operational details.

---

## 1. Architecture and tech stack

### 1.1 What the system is

A fully offline Retrieval-Augmented Generation (RAG) assistant. Company
documents are ingested into a local vector database; questions are answered
by a locally served LLM, grounded in retrieved document chunks, with inline
`[n]` citations. The defining constraint is the **air gap**: after
deployment, nothing may require internet access — which drives almost every
technology choice below.

### 1.2 The pipeline

```
                 ┌────────── INGESTION ──────────┐
Documents ──▶ loaders ──▶ chunker ──▶ embed (bge-m3) ──▶ Qdrant
 (PDF, DOCX, …)  (text +     (512-char    via Ollama        (chunks + payload
                  sections)   recursive)                     + per-doc summaries)

                 ┌────────── QUERY ──────────────┐
Question ──▶ embed ──▶ Qdrant search ──▶ context assembly ──▶ LLM (qwen3)
                        (top-k + margin cut        │              via Ollama
                         + aggregate grouping)     ▼
                                        prompt: system + <documents> + history
                                                   │
                                                   ▼
                                    streamed answer + [n] citations + sources
```

Ingestion: a format-specific **loader** produces clean text with section
metadata (page numbers, slide indexes, headings); the **chunker** splits it
(recursive strategy, 512 chars, 64 overlap, 128 floor); each chunk is
**embedded** by `bge-m3` through Ollama and stored in **Qdrant** with a rich
payload (see `schema.py`). A per-document **summary** is also generated and
stored in a second collection — it routes aggregate queries and briefs the
prompt.

Query: the question is embedded, Qdrant returns the `top_k` nearest chunks, a
**score-margin cut** drops weak hits, and — for aggregate questions ("compare
all candidates") or tag-scoped queries — a **grouped search** additionally
fetches the best chunk per document so roll-ups cover every relevant file.
The chunks are rendered into a `<documents>` block, combined with the system
prompt and recent conversation history, and streamed through the LLM. The UI
renders the stream (optionally including the model's reasoning), maps `[n]`
citations to sources, and persists the conversation.

### 1.3 Runtime topology

Three services, wired by Docker Compose ([deploy/docker-compose.yml](../deploy/docker-compose.yml)):

| Service | Image | Role | Port |
|---------|-------|------|------|
| `qdrant` | qdrant/qdrant (version-pinned) | Vector store + document/tag/conversation persistence | 6333 |
| `ollama` | ollama/ollama (version-pinned) | Serves the LLM and the embedder | 11434 |
| `api` | `dffrnt-assistant:latest` (built from [deploy/Dockerfile](../deploy/Dockerfile)) | FastAPI app + static UI | 8000 |

In **development** the API usually runs on the host (debugger-friendly)
against containerized Qdrant + Ollama. In **production** all three are
containers (`prod` compose profile).

There are two deployment *pathways*, abstracted behind an interface (see
§2, `installer/backends/`):

- **CONTAINER** (Linux, Windows) — everything as above.
- **PORTABLE** (macOS) — Docker's Linux VM has no Metal GPU passthrough, so
  Ollama runs as a **native host process** (Metal is automatic on Apple
  Silicon) while Qdrant + API run in a bundled portable container runtime
  (colima + lima + static docker CLI).

### 1.4 Tech stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| Language | Python ≥ 3.14 | stdlib `tomllib` for config, modern typing |
| Package manager | [uv](https://docs.astral.sh/uv/) | lockfile (`uv.lock`), dependency groups |
| API | FastAPI + uvicorn | thin HTTP layer; logic lives in services |
| Vector DB | Qdrant (`qdrant-client`) | also (ab)used as a plain document store |
| LLM serving | Ollama | `qwen3` family (LLM) + `bge-m3` (embeddings) |
| Ollama client | **stdlib `urllib`** (`ollama.py`) | deliberately no SDK — see FAQ |
| Document parsing | PyMuPDF, python-docx, python-pptx, openpyxl, stdlib `csv` | one library per format; **no LangChain / unstructured** |
| Answer→PDF export | mistune (MD→HTML) + PyMuPDF Story (HTML→PDF) | no extra PDF engine |
| Web UI | Vanilla HTML/CSS/JS, native ES modules | **no npm, no framework, no build step** |
| Manager UI | stdlib `http.server` + static HTML/JS | browser is the GUI toolkit |
| Packaging | Docker + PyInstaller (`dffrnt-manager`) | macOS ships source + vendored CPython instead |
| Tests | pytest (3 suites: unit / eval / integration) | plus a synthetic eval corpus generator |

The unifying philosophy: **minimum dependency surface**. Every dependency
must earn its place, because everything has to ship inside an offline bundle
and keep working with no ability to `pip install` a fix on the target.

---

## 2. Source code structure

```
dffrnt-airgapped-ai-assistant/
├── config.toml               # live config — ALSO frozen into bundles at package time
├── config.toml.example       # annotated template (fallback for a bare checkout)
├── conftest.py               # pytest path setup + --reset-corpus option
├── pyproject.toml            # deps, dependency groups (dev / package), pytest config
├── uv.lock                   # locked dependency versions (committed)
│
├── dffrnt_assistant/         # ─── THE APPLICATION ───
│   ├── config.py             # Settings dataclass: every tunable, env>TOML>default
│   ├── schema.py             # THE shared payload contract (chunk fields, helpers)
│   ├── ollama.py             # stdlib-only Ollama client (embed + generate/stream)
│   ├── rag.py                # RAG pipeline: retrieve → prompt → generate; default system prompt
│   ├── ingest/
│   │   ├── loaders.py        # per-format loaders → text + section metadata
│   │   ├── chunker.py        # fixed / sentence / paragraph / recursive splitting
│   │   ├── tags.py           # hierarchical tag normalization
│   │   ├── pipeline.py       # load → summarize → chunk → embed → store; SUPPORTED_EXTENSIONS
│   │   └── backfill.py       # maintenance CLI: summary backfill, bulk (re-)ingest
│   ├── retrieval/
│   │   ├── store.py          # the one Qdrant wrapper (vector collection)
│   │   ├── retriever.py      # query embedding, top-k + margin + aggregate grouping
│   │   └── doc_store.py      # Qdrant as plain storage: tag taxonomy + conversations
│   ├── api/
│   │   ├── app.py            # FastAPI wiring only; startup builds the singletons
│   │   ├── services.py       # ALL business logic (upload/query/library/delete)
│   │   ├── export.py         # answer Markdown → PDF (mistune + PyMuPDF Story)
│   │   └── audit.py          # append-only JSONL audit log
│   └── ui/                   # vanilla JS web app (no build step)
│       ├── index.html
│       ├── js/               # ES modules: api, chat, library, upload, tags, scope, …
│       └── styles/           # plain CSS: theme, layout, chat, library, tags, …
│
├── installer/                # ─── THE MANAGER (control panel + CLI) ───
│   ├── __main__.py           # `python -m installer` entry: no args → panel, args → CLI
│   ├── cli.py                # argparse CLI: install/start/stop/status/logs/models/…
│   ├── web/server.py         # stdlib HTTP server: 127.0.0.1, token-gated, SSE jobs
│   ├── backends/             # Backend interface + DockerComposeBackend / PortableBackend
│   ├── installers/           # Installer interface + Docker / Portable first-run installers
│   ├── model_store.py        # filesystem ops on the Ollama store (list/export/import)
│   ├── platform_detect.py    # OS/arch/GPU detection → picks the pathway
│   ├── process.py            # subprocess plumbing; BackgroundJob (thread + queue)
│   ├── config.py             # app-root/config discovery, config.toml rewriting
│   └── logging_setup.py      # logs/installer.log
│
├── deploy/                   # ─── PACKAGING (build machine only) ───
│   ├── Dockerfile            # builds the app image with uv
│   ├── docker-compose.yml    # qdrant + ollama + api stack (prod profile); PINNED versions
│   ├── package.sh            # builds dist/: bundle tarball + frozen manager + README
│   ├── package-macos-portable.sh  # vendored CPython + portable runtime for macOS
│   ├── README.md / README.target.md   # build-side docs / target README template
│   ├── data/                 # sample documents (also handy in dev)
│   ├── ollama_models/        # containerized Ollama model store (bind-mounted)
│   └── qdrant_storage/       # dev/prod Qdrant data (gitignored contents)
│
├── tests/
│   ├── unit/                 # fast, offline: chunker, loaders, retriever, CLI, web, …
│   ├── eval/                 # quality suite (pytest -m eval): needs live stack
│   │   ├── corpus_gen.py     # generates the synthetic ground-truth corpus
│   │   ├── cases.py          # the graded question/answer cases
│   │   ├── test_retrieval.py # precision / recall on retrieval
│   │   ├── test_answers.py   # answer correctness, citation coverage, refusals
│   │   └── test_chunking.py  # offline chunk-health checks (run in CI too)
│   └── test_system.py        # integration smoke tests (pytest -m integration)
│
└── .vscode/                  # launch profiles + tasks (see §4)
```

Two files deserve special attention before you change anything:

- **[schema.py](../dffrnt_assistant/schema.py)** is the single shared
  contract: every chunk stored in Qdrant uses exactly those payload fields,
  and every consumer reads them through its helpers. It is what keeps
  ingestion and retrieval from drifting apart. Extend it deliberately;
  never write ad-hoc payload keys.
- **[config.py](../dffrnt_assistant/config.py)** defines every tunable and
  its default. Anything configurable goes here (and in
  `config.toml.example`), never as a scattered constant. Precedence:
  environment variable > `config.toml` > dataclass default.

Layering rules worth preserving: `app.py` contains HTTP wiring only —
business logic goes in `services.py`. The manager's UI layers (`web/server.py`,
`cli.py`) talk only to the `Backend`/`Installer` interfaces, never to
`docker compose` directly — that is what lets the same code manage both
deployment pathways with no OS conditionals in the UI.

---

## 3. Getting set up (Git + VS Code)

### 3.1 Prerequisites

- **Git**, **VS Code** (with the *Python* + *Python Debugger* extensions)
- **[uv](https://docs.astral.sh/uv/)** — the only Python tooling you need
  (it installs/manages Python 3.14 itself)
- **Docker Engine + Compose v2** — for Qdrant/Ollama in dev and everything
  in prod. Your user must be able to run `docker` without sudo.
- Optional but recommended: an NVIDIA GPU (set `gpu = true`); CPU works with
  the small model.

### 3.2 Clone and bootstrap

```bash
git clone https://github.com/ashwathram/dffrnt-airgapped-ai-assistant.git
cd dffrnt-airgapped-ai-assistant
uv sync                        # creates .venv from uv.lock (incl. dev group)
cp config.toml.example config.toml   # then review: gpu flag, llm_model size
```

Pick `llm_model` to match your hardware before first start — the comments in
`config.toml.example` give VRAM figures per size (`qwen3:4b` is CPU-viable;
`14b` wants a 16 GB GPU; `30b-a3b` a 24 GB GPU).

Branch workflow: `main` is the default branch and PR target; feature work
happens on branches (e.g. `dev-installer-integration`). Open VS Code with
`code .` and select the `.venv` interpreter if it isn't picked up
automatically.

### 3.3 Run the dev loop

```bash
uv run python -m installer dev   # Qdrant + Ollama containers, health-waited,
                                 # configured models pulled/ensured
uv run dffrnt-api                # API + UI on the host → http://localhost:8000
```

Or just use the VS Code launch profile **DFFRNT AI Assistant (Dev: host
API)**, which does both (§4). Code changes to the Python API require a
restart (no auto-reload is configured); UI changes (`dffrnt_assistant/ui/`)
are plain static files — refresh the browser.

### 3.4 Run the tests

```bash
uv run pytest                        # unit + offline chunk-health (fast, no stack)
uv run pytest -m eval                # retrieval/answer quality; needs the dev stack up
uv run pytest -m eval --reset-corpus # …wiping the KB and re-ingesting tests/eval/corpus first
uv run pytest -m integration         # smoke tests against a RUNNING API server
```

The default `addopts` in `pyproject.toml` excludes `integration` and `eval`,
so bare `pytest` is always safe offline — that's also what CI runs. The eval
suite grades retrieval precision/recall, answer correctness, citation
coverage, and refusal behaviour against a synthetic corpus generated by
`tests/eval/corpus_gen.py`. Answer tests generate with the local LLM, so a
full pass takes a while.

> **Note:** eval scores are only comparable against the same model and
> settings. If you change `llm_model`, `llm_num_ctx`, chunking, or
> `score_margin`, re-run the suite to establish a fresh baseline before
> judging your change.

---

## 4. Launch profiles (`.vscode/launch.json`)

| Profile | What it does |
|---------|--------------|
| **DFFRNT AI Assistant (Dev: host API)** | The everyday profile. Pre-launch task brings up Qdrant + Ollama (via `python -m installer dev`), then runs the API on the host under `debugpy` — breakpoints anywhere in `dffrnt_assistant/`. |
| **DFFRNT AI Assistant (Prod: Docker container)** | Rebuilds the app image from source, then starts the full containerized prod stack via the manager (`installer start`). Detached — stop with `uv run python -m installer stop`. Use to verify container behaviour. |
| **DFFRNT Control Panel (browser)** | Runs the manager's browser panel under the debugger — for developing the installer/manager itself. Deliberately has **no** pre-launch task: the panel manages the stack, so nothing may pre-start it. |
| **Tests: unit** | `pytest -v` (the offline default suite) under the debugger. |
| **Tests: evaluation (live stack)** | The eval suite with the stack auto-started by the pre-launch task. Skips with instructions if stack/corpus is missing. |
| **Tests: evaluation (reset corpus first)** | Same, but `--reset-corpus`: wipes the document/summary collections and re-ingests `tests/eval/corpus` first. **Destructive to your dev KB.** |
| **Package: AWS deployment** | `deploy/package.sh TARGET_SYSTEM=AWS` — small online bundle into `dist/`. |
| **Package: Offline deployment** | `deploy/package.sh TARGET_SYSTEM=OFFLINE` — air-gapped bundle (images + model store included). |
| **Package: macOS deployment** | OFFLINE bundle + `package-macos-portable.sh arm64`: vendored CPython, manager as source, portable container runtime. The app image must be linux/arm64 for Apple Silicon. |

The pre-launch task **Setup: All prerequisites** ([.vscode/tasks.json](../.vscode/tasks.json))
runs three tasks in parallel: `uv sync`, `mkdir -p data logs`, and
`uv run python -m installer dev` (GPU-aware, health-waited, models ensured).

---

## 5. Things future developers should know

- **The payload schema is load-bearing.** All retrieval filtering (tags,
  filenames, summaries) works off payload fields defined in `schema.py`.
  Adding a feature that needs new per-chunk data means: extend
  `PAYLOAD_FIELDS`, write it in `pipeline.build_payload`, read it through a
  `schema.py` helper, and re-ingest.
- **`llm_num_ctx` is not a detail.** Ollama silently truncates prompts to
  its context window; the 4096 default eats RAG prompts whole. The shipped
  16384 was sized to worst-case retrieval + `llm_num_predict`. If you widen
  retrieval (`top_k`, aggregates) or lengthen history, re-check the budget.
- **The embed model is a one-way door.** Changing `embed_model`/
  `vector_size`/prefixes invalidates every stored vector — that's why the
  manager exposes LLM swapping but deliberately not embedder swapping.
  After any such change: `dffrnt-manager reingest` (or
  `python -m dffrnt_assistant.ingest.backfill --ingest-missing --force`).
- **Generation settings encode hard-won lessons.** `repeat_penalty = 1.1`
  stops the reasoning model looping the same thought until timeout;
  `num_predict = 5000` is the runaway cap that still leaves room for
  thinking *and* answer (3000 guillotined answers). Change them only with
  the eval suite in hand.
- **`config.toml` is frozen into bundles.** `deploy/package.sh` ships the
  repo's *live* `config.toml` — its state at package time (model choice,
  `gpu` flag, prompt) is exactly what a deployment runs. Check it before
  packaging.
- **Compose pins versions on purpose.** Qdrant/Ollama image tags in
  `docker-compose.yml` are pinned; bump them there and re-run the eval
  suite before packaging.
- **The system prompt is a security boundary.** Retrieved documents are
  wrapped in `<documents>` and the prompt instructs the model to treat their
  contents as data — the prompt-injection defence. Keep that instruction
  (and the exact refusal sentence, which the UI/tests rely on) when editing
  prompts, and keep `config.toml`'s prompt in sync with
  `DEFAULT_SYSTEM_PROMPT` in `rag.py`.
- **The API has no authentication.** Anyone who can reach port 8000 can
  read, upload, and delete. Fine on a trusted LAN behind the air gap; adding
  auth is an obvious extension point (do it in FastAPI middleware, and gate
  the destructive endpoints first).
- **Long-running work must not block.** In the manager, anything that runs
  a subprocess to completion goes through `process.BackgroundJob` (worker
  thread + output queue; the web panel drains it over SSE, the CLI passes
  `print`). Follow that pattern for new verbs.
- **The Ollama model store is just files.** `manifests/…/<name>/<tag>` JSON
  plus content-addressed `blobs/sha256-*`. `model_store.py` manipulates it
  directly (list/export/import work with the stack down); only pull/delete
  talk to the running Ollama.
- **Logs to know:** `logs/installer.log` (manager operations),
  `logs/audit.jsonl` (app audit trail), `dffrnt-manager logs <svc>`
  (containers).

## 6. Extension recipes

**Add a document format.** Write a loader in `ingest/loaders.py` returning
the standard Document dict (text + sections with page/heading metadata),
register the extension in `load_file`'s dispatch and in
`SUPPORTED_EXTENSIONS` (`ingest/pipeline.py`), add a unit test with a
fixture file, and (optionally) surface the extension in the UI upload
validator (`ui/js/upload.js`).

**Add an API endpoint.** Put the logic in `api/services.py` (raise
`UserError(status, detail)` for client errors), add the route in
`api/app.py` as a thin adapter, wire the UI call in `ui/js/api.js`, and
consider whether the action belongs in the audit log.

**Add a manager verb.** Implement it on the `Backend` interface (both
pathways if applicable), expose it in `cli.py` (argparse) and
`web/server.py` (+ the panel UI in `installer/web/static/`), and run it
through `BackgroundJob` if it can take more than a moment.

**Tune retrieval quality.** The knobs are `top_k`, `score_margin`,
`aggregate_group_limit/size`, and the chunking block. The workflow is:
change one thing → `pytest -m eval --reset-corpus` → compare. Never tune by
vibes; the margin cut especially is corpus-dependent.

---

## 7. FAQ — design choices and trade-offs

**Why no LangChain / LlamaIndex / RAG framework?**
The pipeline is ~a dozen small modules; a framework would add hundreds of
transitive dependencies to an air-gapped bundle, obscure the retrieval logic
this project exists to tune, and churn APIs faster than a student-team
handover cycle. Trade-off: we reimplement loaders and prompt assembly
ourselves — accepted, because those are exactly the parts we want control
over (and they're covered by unit + eval tests).

**Why a stdlib-only Ollama client (`urllib`)?**
One fewer dependency to vendor, and the Ollama HTTP API is small (two
endpoints used). Trade-off: no connection pooling or typed responses;
mitigated by the client being ~200 lines with tests.

**Why Ollama rather than vLLM / llama.cpp directly?**
Ollama gives model lifecycle management (pull, quantized model store,
keep-alive), a stable HTTP API, and one identical serving story on Linux
containers *and* native macOS with Metal. Trade-off: less throughput tuning
than vLLM — irrelevant at single-office concurrency.

**Why Qdrant?**
Runs as a single small container fully offline, has payload filtering (tags
scoping needs it), grouped search (the aggregate-query feature), and
persistent named collections. Trade-off: heavier than an embedded library
(e.g. sqlite-vec), but it's also reused as the app's only datastore —
see next question.

**Why are tags and conversations stored in Qdrant with dummy vectors?**
`doc_store.py` attaches a throwaway 1-D vector because Qdrant requires one,
then only ever upserts/fetches by id. This keeps the deployment at **zero
additional databases** — no SQLite file to migrate, no second container.
Trade-off: mildly unidiomatic; documented in the module docstring.

**Why a vanilla-JS UI with no build step?**
An air-gapped target can't `npm install`, and a build pipeline is one more
thing a future team must resurrect before touching the UI. Native ES modules
+ plain CSS mean "edit file, refresh browser" forever. Trade-off: no
reactivity framework — state is managed manually in `js/state.js`, which is
fine at this UI's size but would strain if the UI grew much larger.

**Why is the model `qwen3` and the embedder `bge-m3`?**
`qwen3` ships in sizes spanning CPU-only to 24 GB GPU with strong multilingual
+ reasoning behaviour under Ollama; `bge-m3` is a robust multilingual
embedder with 1024-dim vectors and no task prefixes. Both are swappable in
config — but swapping the embedder invalidates the index (§5), and eval
baselines are per-model.

**Why does the manager render in a browser instead of Tk/Qt?**
The browser is the one GUI runtime every target already has. A Tk build
needs per-platform freezing and made macOS support painful; a localhost web
panel is identical everywhere, works over SSH tunnels, and shares its
plumbing with the headless CLI. Trade-off: a local HTTP server needs a
security model — hence loopback-only binding + per-session token.

**Why is `dffrnt-manager` a PyInstaller binary on Linux/Windows but
source + vendored CPython on macOS?**
Targets must not need Python. PyInstaller freezes per-platform, and the
team had no Mac in the build loop — so the macOS bundle carries the manager
as source plus a relocatable CPython (python-build-standalone) and a shell
launcher. Same UX (`./dffrnt-manager`), no Mac needed to build.

**Why Python ≥ 3.14?**
Recent stdlib carries weight here: `tomllib` (config), modern typing, and
current security fixes for a long-lived offline install. uv makes the
interpreter version a non-issue for developers.

**Why FastAPI?**
Streaming responses (ndjson token streams), static file mounts for the UI,
pydantic validation at the edge, and wide familiarity for onboarding teams.
The app deliberately keeps it to a thin adapter so a framework swap would be
contained to `app.py`.

**Why is there a separate summaries collection?**
Chunk-level search alone misses "about-ness": aggregate questions ("compare
all proposals") need to know *which documents* are relevant, not just which
512-char chunks. Per-document summaries give a routing signal and prompt
briefing. Trade-off: summaries are LLM-generated at ingest time (slower
ingestion) and must be backfilled for pre-existing docs
(`ingest/backfill.py`).

**Why does bare `pytest` skip the interesting tests?**
So CI and any offline checkout stay green with no stack. The quality suite
is opt-in (`-m eval`) because it needs Qdrant + Ollama and real generation
time. The skip messages tell you exactly how to bring the stack up.

**Where would authentication go if we added it?**
FastAPI dependency/middleware in `app.py` gating the mutating routes first
(upload/delete/tags), then the query routes. The manager panel already has
its token model and needs nothing. Remember the UI's `js/api.js` is the
single place all fetches go through — one spot to attach credentials.

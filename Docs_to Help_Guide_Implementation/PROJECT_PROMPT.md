# Project Status

This document is the shared working log for the project. It is meant to stay current while the agent and user collaborate.

## Update This File When...
- a task starts
- a code change lands
- a test or smoke check finishes
- a blocker appears or clears
- a plan changes
- a decision is made
- the next step changes

## Current Snapshot
- Last updated: 2026-05-28
- Owner: user and agent together
- Rule: keep this file synced with real project state, not template state
- Refresh behavior: the agent should update this file at the start and end of meaningful work

## Current Goal
- Build an offline RAG assistant with a complete upload and ingestion API layer.
- Support Snowflake-like drag-and-drop file uploads with job tracking and background ingestion.
- Keep metadata tagging, incremental ingest, and Qdrant retrieval filters in reusable application code.
- Keep `scripts/database_validation.py` as a validation-only runner.
- Provide persistent chat storage for multi-chat sessions (like ChatGPT).

## Active Product Requirements
- Support drag-and-drop raw file intake for end users.
- Let users tag files with metadata so retrieval can be narrowed later.
- Keep the database layer incremental so updates are fast.
- Improve retrieval accuracy and response speed by indexing and filtering well.
- Keep the foundation solid for the frontend, local LLM, and higher-level RAG pipeline work done by teammates.
- Treat the current work as the database/indexing foundation for the offline assistant.

## What Has Been Built
- `src/ingestion/metadata.py` loads JSON and CSV/TSV sidecar metadata.
- `src/ingestion/ingest.py` contains the reusable ingestion pipeline.
- `src/ingestion/cli.py` is the production CLI entrypoint.
- `src/vector_store/qdrant_store.py` supports metadata filters during search.
- `scripts/database_validation.py` now calls shared `src/` logic and stays focused on validation output.

## Metadata That Is Stored On Each Chunk
- `filename`
- `source_file`
- `file_type`
- `text`
- `document_type`
- `department`
- `client_project`

## Working Agreement For This File
- Treat this file as the running source of truth.
- The agent must update this file every time it makes a meaningful change.
- Update it before and after meaningful work.
- Keep the latest verification and current state near the top.
- Record concrete commands and outcomes, not vague summaries.

## Current State
- The production ingestion path runs through `src/ingestion/cli.py` and is also exposed via HTTP API.
- The validation script is no longer the place where ingestion logic lives.
- **Upload API Layer** (NEW): Complete `/api/upload` endpoint with:
  - Multi-file upload support
  - ZIP archive extraction (safe, with path-traversal protection)
  - Background ingestion using FastAPI BackgroundTasks
  - SQLite job tracking (`src/ingest_jobs.py`) with statuses: queued → processing → completed/failed
  - Job status endpoints: `GET /api/ingest-status/{job_id}` and `GET /api/ingest-status?limit=20`
  - Tag and metadata support (hierarchical tags like `Department/HR/Policy`)
- **Chat Storage**: Moved `src/backend/chat_store.py` → `src/chat_store.py` for cleaner organization.
- **Chat API**: Endpoints for creating chats, listing chats, and appending messages (multi-chat support).
- Metadata tagging is now part of the shared ingestion pipeline.
- Metadata filters work in Qdrant search.
- Incremental ingest skips unchanged files using the checksum cache.
- Stale vectors are deleted when a file changes.
- `scripts/database_validation.py` validates the ingestion pipeline independently.

## Last Verified
- `scripts/database_validation.py --limit-files 2 --incremental` completed successfully and wrote `Files/database_validation.md`.
- `pytest tests/test_metadata_ingest.py::test_metadata_ingest_and_filtering -q` passed.
- Real Qdrant smoke ingest ran successfully through `src/ingestion/cli.py`.
- Metadata was present in Qdrant payloads.
- Metadata filters returned the expected result set.
- The CLI exited with success and printed `Ingested 2 chunks into collection ingest_smoke_cli`.
- `py_compile` passed for all ingestion, embedding, processing, and vector_store modules.
- `pylint src/ --fail-under=7.0` passed.
- Upload API implementation verified: `py_compile` passed for `src/api/app.py`, `src/ingest_jobs.py`, `src/chat_store.py`.
- Code compiles without errors; ready for integration testing via `tests/test_upload_api.py`.

## Commands Already Used For Verification
```powershell
Set-Location 'C:/DTI 5902/dffrnt-airgapped-ai-assistant'
& '.\.venv\Scripts\python.exe' 'src\ingestion\cli.py' --source-root <temp-data> --metadata-file <temp-metadata.json> --state-file <temp-state.json> --collection-name 'ingest_smoke_cli' --incremental
```

```powershell
$env:PYTHONPATH = (Join-Path $PWD 'src')
& '.\.venv\Scripts\python.exe' -c "from vector_store.qdrant_store import QdrantStore; ..."
```

## Completed Work
- Created a reusable metadata loader in `src/ingestion/metadata.py`.
- Moved ingestion logic into `src/ingestion/ingest.py`.
- Added a production CLI in `src/ingestion/cli.py`.
- Kept the validation runner thin and import-based.
- Added unit and smoke tests for metadata storage, retrieval filtering, and incremental behavior.
- Added docs with JSON and CSV sidecar examples plus exact smoke-test commands.
- **NEW (Upload API Layer)**:
  - Created `src/ingest_jobs.py`: SQLite-backed job tracking system for ingestion tasks.
  - Moved `src/backend/chat_store.py` → `src/chat_store.py`: Persistent multi-chat session storage.
  - Enhanced `src/api/app.py`: Added `/api/upload` endpoint with multi-file, ZIP, tags, and background ingestion support.
  - Added job status endpoints: `GET /api/ingest-status/{job_id}` and `GET /api/ingest-status` for tracking.
  - Implemented safe ZIP extraction with path-traversal protection.
  - Integrated with existing ingestion pipeline (embeddings, Qdrant, metadata, tags).
  - Created `tests/test_upload_api.py`: Comprehensive test suite demonstrating all upload capabilities.
  - Created `docs/UPLOAD_API.md`: Complete API documentation with 9 curl examples.

## In Progress
- Keep this file updated as the project evolves.
- Decide whether to package the CLI as a console entry point later.
- Investigate the remaining `mypy` failure on `src/` when needed.

## Backend Models & API Contract

- **ChatStore** (`src/backend/chat_store.py`): persistent chat threads and messages. APIs needed:
	- `POST /api/chats` -> create chat (payload: `{title}`) -> `{id,title,created_at}`
	- `GET  /api/chats` -> list chats -> `[{id,title,created_at}]`
	- `GET  /api/chats/{chat_id}` -> get chat with messages -> `{id,title,messages}`
	- `POST /api/chats/{chat_id}/messages` -> append message (payload: `{role,text}`) -> `{role,text,ts}`

- **Destination / Workspace** (`src/ingestion/destination.py`): workspace/schema-based collection naming. CLI accepts `--workspace` and `--schema`; frontend should present a Snowflake-like chooser. Backend mapping:
	- `POST /api/destinations` -> create/list workspaces & schemas (payload: `{workspace,schema}`)
	- collection names are derived via `make_collection_name(workspace,schema,base)`

- **Hierarchical Tags** (`src/ingestion/tags.py`, `src/ingestion/metadata.py`):
	- frontend sends `tags` (leaf paths) or `tag_paths` (explicit paths). Examples: `Department/HR/Policy`, `Client/A`.
	- ingestion expands and stores both `tags` and `tag_paths` on each chunk payload for filterable search.
	- search filter supports matching on `tag_paths` (ancestor or exact match).

## API Examples (minimal)

- Upload + tags (frontend -> backend ingest endpoint):

	Request: `POST /api/upload` (multipart form)
	- fields: `file`, `workspace`, `schema`, `tags` (json array or comma-separated)

	Response: `200 OK` `{ "collection": "ingest_workspace_schema_20260528...", "uploaded": 1 }`

- Search with tag filter:

	Request: `POST /api/search` JSON body:
	```json
	{
		"query": "policy change",
		"top": 10,
		"filter": {"must": [{"key": "tag_paths", "match": {"value": "Department/HR"}}]}
	}
	```

	Response: `200 OK` `{ "results": [{"id","score","payload"}, ...] }`

## How this maps to the frontend

- Upload flow: choose `workspace` → choose `schema` → add hierarchical tags → upload file.
- Search flow: query box + tag-facet filters (use `tag_paths` for ancestor matches).
- Chat flow: list chats, create chat, send messages (persisted via ChatStore). Chat threads are independent and can be associated with a `workspace` or `collection` id when needed.

## Next Step (recommended) - COMPLETED
- ✅ HTTP API (FastAPI) implementing the endpoints is now complete.
- ✅ `/api/upload` with multi-file and ZIP support done.
- ✅ `/api/search` already implemented.
- ✅ `/api/chats` set for multi-chat sessions done.
- ✅ `/api/destinations` for workspaces/schemas already implemented.

## Recommended Next Work
1. **Integration Testing**: Run `python tests/test_upload_api.py` to validate end-to-end upload → ingestion → vector storage flow.
2. **Frontend Development**: Wire up the React/Vue/etc frontend to use these endpoints for Snowflake-like UX.
3. **Production Hardening**: Add Celery/Redis for parallel ingestion, WebSocket for progress, authentication layer.
4. **Optional Enhancements**: TAR/GZIP support, job retry logic, bulk search UI.

## Air-gap Decisions and Actions

- **Embedder behavior (current)**: The repository documents local-model support but the current `Embedder` implementation in `src/embeddings/embedder.py` is flexible: it will attempt to load a model from `EMBEDDER_LOCAL_PATH` when provided, but will also attempt to download a model from the Hugging Face hub if a local model is not available. When no real model is available, the embedder falls back to a deterministic stub embedding. In short, the code allows remote fetches by default; the docs describe air-gap best-practices but the runtime does not enforce fail-fast behavior yet.
- **Env flags (documented, not enforced by code)**:
  - `EMBEDDER_LOCAL_PATH` — filesystem path to sentence-transformers model files (used when present).
  - `DISABLE_HF_DOWNLOAD` — documented flag; intended to disallow automatic huggingface downloads.
  - `FAIL_ON_EXTERNAL_FETCH` — documented flag; intended to cause fail-fast behavior when external fetches would be required.
- **Documentation**: `docs/airgap.md` was added with steps to prepare model files, a wheelhouse, and a pre-pulled Qdrant image for offline hosts.

Follow-up work (recommendations):
- If you want the runtime to be strict (no network fetches), update `src/embeddings/embedder.py` to enforce `DISABLE_HF_DOWNLOAD`/`FAIL_ON_EXTERNAL_FETCH` (fail-fast) — I can implement this change if you choose.
- Create a wheelhouse (`pip download -r requirements.txt`) and add an install script for offline hosts.
- Provide a saved `qdrant.tar` and a `docker load`/`docker run` script in `docs/`.
- Audit code and third-party libs for any remaining runtime HTTP calls and add explicit checks or fail-fast guards where appropriate.

## Blockers
- None blocking the current ingestion, metadata, and upload API work.
- Integration testing should be done to validate Qdrant storage and retrieval with the new upload layer.

## Next Step
- If the next task changes the pipeline or adds new features, update this file first so the project state stays aligned.
- Current focus: integration testing of upload API, then frontend development.

## Notes
- The project is an offline RAG assistant built around ingestion, chunking, embeddings, Qdrant indexing, metadata tagging, retrieval filters, and smoke tests.
- Keep reusable logic in `src/`.
- Keep validation and reporting scripts thin.
- Prefer concrete evidence from the latest run over assumptions.
- Current requirement focus: drag-and-drop file intake, user tagging, incremental database updates, and strong retrieval foundation.

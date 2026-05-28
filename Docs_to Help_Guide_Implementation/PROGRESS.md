# Project Progress Tracker

Last updated: 2026-05-24

This file tracks what has been done, what is currently in progress, and what remains to be done. Keep this file updated as you complete tasks so teammates can see status at a glance.

## Completed
- Repository top-level review and README read.
- `requirements.txt` examined (currently placeholder).
- Explored `src/` modules: `embedder`, `ingestion/loaders.py`, `processing/chunker.py`, `vector_store/qdrant_store.py`.
- Updated `tools/extract_pdf.py` to accept a path and used it to extract `DFFRNT Pitch Presentation.pdf` text.
- Created the project virtual environment using Python 3.14 and verified `\.venv\Scripts\python.exe` -> Python 3.14.5.
- Installed `PyPDF2` into the venv to support PDF extraction.
- Inspected `C:\CSI5180\CSI5180_VA_Project` for reference architecture and documentation style.
- Added documentation files to this folder:
  - `CONTRIBUTING.md`
  - `RUNNING.md`
  - `ARCHITECTURE.md`
  - `ROADMAP.md`
  - `MAINTENANCE.md`

## In Progress
- Summarizing docs and mapping the presentation into a concrete implementation plan (action items listed in `ROADMAP.md`).
- Decide owners for short-term tasks and assign them in `ROADMAP.md`.

## Planned (next priorities)
- Create `scripts/ingest_presentation.py` to demonstrate end-to-end ingestion (loader -> chunker -> embedder -> upsert to Qdrant).  
- Pin `requirements.txt` with inferred packages and sensible versions for offline packaging.  
- Add a minimal `app/streamlit_app.py` demo that queries the vector store and displays source snippets.  
- Add `models/VERSIONS.md` and guidelines for storing model binaries.
- Add CI checks (basic lint and tests) and a `Makefile` or `scripts/` helper entrypoints.

## Blockers / Notes
- Large model binaries and wheels must be pre-downloaded for air-gapped deployment (see `MAINTENANCE.md`).
- Some local files (e.g., trained models) may exist in other local checkouts but are not tracked by git; maintainers should add a note of any local-only artifacts.

## How to update this file
- Edit this file directly in the repo when you finish a task; include your name and date for the change.
- For larger changes, open a PR that updates the `ROADMAP.md` and `PROGRESS.md` together.

## Owners / Contacts
- Project Sponsor: Dominira Saul (see presentation)
- Technical Advisor: Yiwei Lu
- Suggested maintainers: add names in `ROADMAP.md` next to items


---

If you'd like, I can now implement one of the planned items (ingestion script, pinned `requirements.txt`, or the Streamlit demo). Tell me which to start with.
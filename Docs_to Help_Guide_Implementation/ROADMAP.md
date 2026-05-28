# Roadmap and Next Actions

This roadmap lists features, priorities, and owners for the DFFRNT Air-Gapped Assistant.

Priority: High (MVP)
- Implement ingestion -> embed -> vector store pipeline (Owner: TBD)
- Minimal query UI (Streamlit) to ask questions and show source snippets (Owner: TBD)
- RFP/resume generator agent (Owner: TBD)

Priority: Medium
- Local LLM runner integration (Ollama / local runtime)
- Streamlined offline model packaging and install docs
- Source attribution UI and hallucination mitigation

Priority: Low / Later
- Multi-user permissions and role-based access
- Advanced analytics and usage telemetry (offline-safe)

Short-term tasks (next 2 weeks)
- Add end-to-end example that ingests `Docs_to Help_Guide_Implementation/DFFRNT Pitch Presentation.pdf` and runs a sample query. (owner: you)
- Finalize `requirements.txt` with pinned packages and add instructions for creating an air-gapped wheel cache.
- Create `scripts/ingest_presentation.py` that demonstrates the ingestion flow.

How to pick an owner
- Add your GitHub/Teams handle next to the item and update progress in PRs.

If you want, I can start by adding the ingestion example and a `scripts/ingest_presentation.py` demo.
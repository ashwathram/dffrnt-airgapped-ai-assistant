# Maintenance and Model Management

This file describes routine tasks for maintainers: updating models, backing up data, and preparing offline artifacts for air-gapped installs.

Model updates
- Store model binaries under `models/` and list versions in `models/VERSIONS.md` (create when needed).
- To update a model, run the training scripts (or copy new binaries) and record the change in `models/VERSIONS.md` with date and owner.

Backing up data
- Regularly copy `database/raw/` and `external_datasets/` to a secure backup location.

Preparing an air-gapped bundle
1. Use `pip download -r requirements.txt -d wheelhouse/` on a machine with internet.
2. Copy `wheelhouse/` and `models/` to the air-gapped host.
3. On the air-gapped host, install from wheels: `pip install --no-index --find-links wheelhouse -r requirements.txt`.

Database maintenance
- Qdrant data lives in a local volume when run via Docker. Back up the volume regularly.

Troubleshooting
- If the ingestion pipeline fails, check: PDF readers, Pandas CSV parsing, and that the `Embedder` model is available or fallback is acceptable.
- For LLM issues: confirm the LLM runner binary (Ollama or other) and model files are present and compatible.

Contact and owners
- List the internal maintainers and the technical advisor in the project README and in this document when finalized.
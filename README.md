# DFFRNT Air-Gapped AI Assistant

A private, fully offline RAG assistant for DFFRNT's internal knowledge. It
ingests company documents (proposals, resumes, policies, spreadsheets, …) and
answers questions with grounded, citation-backed responses. Everything runs
locally — **Ollama** serves the LLM (`qwen3` family) and embeddings (`bge-m3`),
**Qdrant** stores the vectors — so no data leaves the machine.

## Documentation

Detailed documentation lives in [doc/](doc/) and is the source of truth:

| Guide | For |
|-------|-----|
| [Developer Guide](doc/Developer_Guide.md) | Architecture, source layout, dev workflow, config internals, extension recipes, design FAQ |
| [Installer Guide](doc/Installer_Guide.md) | Deploying a bundle on a target machine, SSH access, troubleshooting |
| [User Guide](doc/User_Guide.md) | Using the assistant and `dffrnt-manager`, routine tasks, full `config.toml` reference |

Packaging a deployment bundle is covered in [deploy/README.md](deploy/README.md);
the manager/control-panel internals in [installer/README.md](installer/README.md).

## Set up (clone + VS Code)

**Prerequisites:** [Git](https://git-scm.com/), [uv](https://docs.astral.sh/uv/)
(installs and manages Python 3.14 itself), and Docker Engine + Compose v2 (your
user must run `docker` without sudo). VS Code with the *Python* + *Python
Debugger* extensions. An NVIDIA GPU is optional (`gpu = true`); CPU works with
the small model.

```bash
git clone https://github.com/ashwathram/dffrnt-airgapped-ai-assistant.git
cd dffrnt-airgapped-ai-assistant
uv sync                              # creates .venv from uv.lock (incl. dev group)
cp config.toml.example config.toml   # then review: gpu flag, llm_model size
code .                               # select the .venv interpreter if not auto-picked
```

Pick `llm_model` to match your hardware before first start — the comments in
`config.toml.example` give VRAM figures per size (`qwen3:4b` is CPU-viable,
`14b` wants a 16 GB GPU, `30b-a3b` a 24 GB GPU).

## Run

```bash
uv run python -m installer dev   # Qdrant + Ollama containers, health-waited, models ensured
uv run dffrnt-api                # API + UI at http://localhost:8000
```

Or use the VS Code launch profile **DFFRNT AI Assistant (Dev: host API)**, which
does both. See the [Developer Guide](doc/Developer_Guide.md#4-launch-profiles-vscodelaunchjson)
for every launch profile.

## Tests

```bash
uv run pytest                # unit + offline chunk-health (fast, no stack; this is what CI runs)
uv run pytest -m eval        # retrieval + answer quality; needs Qdrant + Ollama up
uv run pytest -m integration # smoke tests against a running API server
```

Bare `pytest` is always safe offline. The eval suite grades retrieval, answer
correctness, citation coverage, and refusals against a synthetic corpus — see
the [Developer Guide](doc/Developer_Guide.md#34-run-the-tests).

## Deploy

`deploy/package.sh` builds a three-file bundle (tarball + the frozen
`dffrnt-manager` binary + README) for either an air-gapped target (**OFFLINE**:
images and models included) or an online one (**AWS**: pulls at deploy time).
The target needs only Docker. See [deploy/README.md](deploy/README.md).

## Technical caveats

- **No authentication.** Anyone who can reach the API port can query, upload,
  and delete. Expose it only to trusted networks (fine behind the air gap).
- **The embed model is a one-way door.** Changing `embed_model` / `vector_size`
  invalidates every stored vector and requires re-ingesting all documents —
  which is why the manager swaps the LLM but not the embedder.
- **`config.toml` is frozen into bundles.** `deploy/package.sh` ships the repo's
  *live* `config.toml`; its state at package time is exactly what the deployment
  runs. Check it before packaging.
- **`llm_num_ctx` matters.** Ollama silently truncates prompts to its context
  window; the shipped 16384 is sized to worst-case retrieval — re-check the
  budget if you widen retrieval or lengthen history.
- **Compose pins Qdrant/Ollama versions on purpose.** Bump them in
  `deploy/docker-compose.yml` and re-run the eval suite before packaging.
- **GPU mode needs host support.** `gpu = true` requires the NVIDIA driver +
  Container Toolkit (Linux/Windows); the manager refuses GPU mode without them.
  macOS uses Metal automatically via the native-Ollama pathway.
</content>
</invoke>

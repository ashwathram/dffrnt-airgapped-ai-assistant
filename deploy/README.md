# Deployment

Package the app into a single tarball + installer + README, copy those three files
to the target, and install. The app ships as a Docker image, so the target needs
**only Docker** — no Python, uv or pip. Two flavours:

- **OFFLINE** — for an air-gapped box. Caches the app image, the Qdrant/Ollama
  base images, and the Ollama model store, so installing needs no internet.
- **AWS** (online) — ships only the app image; the installer pulls the base images
  and models at deploy time, keeping the bundle small.

## 1. Build (networked machine, matching the target OS/arch)

```bash
# OFFLINE: vendor the models first, then point the packager at the model store
ollama pull qwen3:4b && ollama pull bge-m3
deploy/package.sh ~/.ollama/models OFFLINE

# AWS / online: no local model store needed
deploy/package.sh TARGET_SYSTEM=AWS
```

Both parameters accept positional or `KEY=VALUE` form, in any order:

```bash
deploy/package.sh OLLAMA_MODELS_DIR=deploy/ollama_models TARGET_SYSTEM=OFFLINE
```

`package.sh` builds the app image from [Dockerfile](Dockerfile) and reads the
models to vendor/pull from `config.toml.example` (`llm_model` + `embed_model`). It
writes exactly three files to `dist/` and nothing else:

```
dist/
  dffrnt-offline.tar.gz   (or dffrnt-aws.tar.gz)
  install.sh
  README.md
```

Env: `APP_IMAGE` (default `dffrnt-assistant:latest`), `OUT_DIR` (default `dist`).

## 2. Transfer

Copy the three files in `dist/` to the target by approved means (USB, one-way
transfer, etc.), keeping them together.

## 3. Install & run (target)

```bash
./install.sh                 # checks prereqs, unpacks, loads images, starts the stack
cd dffrnt && ./run.sh status # UI at http://localhost:8000
```

See the generated `README.md` next to the tarball for the target-side details.

## Files

| File | Role |
|------|------|
| `package.sh` | Packager — builds the bundle + installer + README into `dist/` |
| `install.sh` | Installer — deploys from the tarball (shipped in `dist/`) |
| `run.sh` | Runner — manages the containers + API (shipped inside the tarball) |
| `Dockerfile` | Builds the app image (`dffrnt-assistant:latest`) with uv |
| `docker-compose.yml` | Qdrant + Ollama + API (`prod` profile) stack |
| `README.target.md` | Template for the target-side `README.md` (filled in by `package.sh`) |

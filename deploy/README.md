# Deployment

Package the app into a single tarball + the `dffrnt-manager` binary + README,
copy those three files to the target, and install. The app ships as a Docker
image and the manager is a frozen binary, so the target needs **only Docker** —
no Python, uv, pip, or shell scripts. Two flavours:

- **OFFLINE** — for an air-gapped box. Caches the app image, the Qdrant/Ollama
  base images, and the Ollama model store, so installing needs no internet.
- **AWS** (online) — ships only the app image; the installer pulls the base images
  and models at deploy time, keeping the bundle small.

## 1. Build (networked machine, matching the target OS/arch)

```bash
# OFFLINE: vendor the models first, then point the packager at the model store
ollama pull qwen3:14b && ollama pull bge-m3
deploy/package.sh ~/.ollama/models OFFLINE

# AWS / online: no local model store needed
deploy/package.sh TARGET_SYSTEM=AWS
```

Both parameters accept positional or `KEY=VALUE` form, in any order:

```bash
deploy/package.sh OLLAMA_MODELS_DIR=deploy/ollama_models TARGET_SYSTEM=OFFLINE
```

`package.sh` builds the app image from [Dockerfile](Dockerfile) and freezes the
repo's **live `config.toml`** into the bundle — the state of that file at package
time (models, `gpu` flag, prompt, retrieval settings) is exactly what the
deployment runs, and `llm_model` + `embed_model` are the models it vendors/pulls
(`config.toml.example` is only the fallback for a bare checkout). The Qdrant and
Ollama base images are version-pinned in [docker-compose.yml](docker-compose.yml);
bump them there and re-run the eval suite before packaging. `package.sh` writes
exactly three files to `dist/` and nothing else:

```
dist/
  dffrnt-offline.tar.gz   (or dffrnt-aws.tar.gz)
  dffrnt-manager          (frozen installer + control panel; browser UI and headless CLI)
  README.md
```

Env: `APP_IMAGE` (default `dffrnt-assistant:latest`), `OUT_DIR` (default `dist`).

## 2. Transfer

Copy the three files in `dist/` to the target by approved means (USB, one-way
transfer, etc.), keeping them together.

## 3. Install & run (target)

```bash
./dffrnt-manager install           # checks prereqs, unpacks, loads images, starts the stack
cd dffrnt && ./dffrnt-manager status   # UI at http://localhost:8000
```

Headless boxes get the full CLI (`install`, `start`, `stop`, `status`, `logs`,
`audit`, `reingest`, `models ...`); running `./dffrnt-manager` with no
arguments serves the browser control panel on 127.0.0.1 and opens it
(`panel --no-browser` prints the URL instead — SSH tunnels).

See the generated `README.md` next to the tarball for the target-side details.

## Files

| File | Role |
|------|------|
| `package.sh` | Packager — freezes `dffrnt-manager` (from `installer/`) and builds the bundle + README into `dist/` |
| `Dockerfile` | Builds the app image (`dffrnt-assistant:latest`) with uv |
| `docker-compose.yml` | Qdrant + Ollama + API (`prod` profile) stack |
| `README.target.md` | Template for the target-side `README.md` (filled in by `package.sh`) |

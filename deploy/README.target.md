# DFFRNT AI Assistant — deployment bundle (@MODE@)

This folder contains everything needed to deploy the assistant:

- `@NAME@.tar.gz` — the application bundle
- `install.sh` — the installer
- `README.md` — this file

Target: **@MODE@**  ·  Models: **@MODELS@**

The app runs as a Docker container, so the target needs **only Docker** (Engine +
the Compose v2 plugin) — no Python, uv or pip.

## Install

```bash
./install.sh                 # unpacks to ./dffrnt and brings the stack up
./install.sh /opt/dffrnt     # ...or choose an install directory
```

The installer checks prerequisites and reports exactly what is missing if a check
fails. It then unpacks the bundle, loads the container image(s), and starts the
Qdrant + Ollama + API stack — pulling the base images and models the first time on
an online build.

> **@MODE@ build.** An OFFLINE bundle carries every image and the Ollama model
> store, so install needs no internet. An AWS bundle ships only the app image and
> pulls the Qdrant/Ollama base images and the models from the internet at deploy
> time, which keeps it small.

## Run

A `dffrnt_ctrl_panel.sh` is placed in the install directory. Run it with no
argument for an interactive menu, or pass a command directly — it manages the
runtime the same way the VS Code tasks do (the containers plus the API):

```bash
cd dffrnt                       # or your chosen install dir
./dffrnt_ctrl_panel.sh          # interactive menu
./dffrnt_ctrl_panel.sh start    # bring the whole stack up
./dffrnt_ctrl_panel.sh stop     # stop all containers
./dffrnt_ctrl_panel.sh restart
./dffrnt_ctrl_panel.sh status   # container + API health
./dffrnt_ctrl_panel.sh logs     # follow container logs (optionally: ./dffrnt_ctrl_panel.sh logs api)
./dffrnt_ctrl_panel.sh audit    # follow the app audit trail (logs/audit.jsonl)
./dffrnt_ctrl_panel.sh reingest # force re-ingest every stored document in the live API
```

The UI is at <http://localhost:8000>.

## Configuration

Edit `config.toml` in the install directory, then `./dffrnt_ctrl_panel.sh restart`. It is the
single source of truth for the LLM/embed models, prompt, and retrieval settings,
and it drives the host ports and GPU acceleration (set `environment = "local-cuda"`
or `gpu = true` for NVIDIA GPUs — requires the NVIDIA Container Toolkit on the
host). The API container always serves on port 8000 internally.

Switching `llm_model`/`embed_model` and restarting pulls the new model (online
builds) and removes the previously configured model from the cache, so disk
usage doesn't grow with every switch. An OFFLINE bundle must have already
vendored the new model at package time (`deploy/package.sh`) — offline installs
have no internet to pull one on demand.

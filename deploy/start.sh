#!/usr/bin/env bash
#
# Dev helper: bring up the Qdrant + Ollama containers only (GPU-aware), so the
# API can run on the host — e.g. the VSCode debugger — against them. The full
# containerized stack, including the API, is run by run.sh; this script is
# dev-only and is not shipped in deployment bundles.
#
# GPU is enabled when config.toml's `gpu` flag is true (e.g. environment =
# "local-cuda"); the device reservation is injected here, so there is a single
# compose file with no separate GPU variant.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"

# Pick a Python that can import the package: repo venv, else system.
PY="python3"
[ -x "$ROOT/.venv/bin/python" ] && PY="$ROOT/.venv/bin/python"

# Locate config.toml: explicit env var, then repo root.
if [ -z "${DFFRNT_CONFIG:-}" ] && [ -f "$ROOT/config.toml" ]; then
  DFFRNT_CONFIG="$ROOT/config.toml"
fi
export DFFRNT_CONFIG="${DFFRNT_CONFIG:-}"

# Resolve ports + GPU through the package (honours env > config.toml > defaults).
readarray -t CFG < <(PYTHONPATH="$ROOT" "$PY" -c "
from dffrnt_assistant.config import load_settings
s = load_settings()
print(s.ollama_url.rsplit(':', 1)[-1])
print(s.qdrant_url.rsplit(':', 1)[-1])
print('1' if s.gpu else '0')
")
export OLLAMA_PORT="${CFG[0]}"
export QDRANT_PORT="${CFG[1]}"
GPU="${CFG[2]}"

# No --profile prod, so the api service stays down: only qdrant + ollama come up.
COMPOSE=(docker compose -f "$HERE/docker-compose.yml")

MODE="CPU"; [ "$GPU" = "1" ] && MODE="GPU"
echo ">> $MODE mode (from config.toml) — dev services: ollama:$OLLAMA_PORT qdrant:$QDRANT_PORT"

if [ "$GPU" = "1" ]; then
  # Inject the GPU reservation via a stdin override so there is a single compose file.
  printf 'services:\n  ollama:\n    gpus: all\n' | "${COMPOSE[@]}" -f - up -d
else
  "${COMPOSE[@]}" up -d
fi

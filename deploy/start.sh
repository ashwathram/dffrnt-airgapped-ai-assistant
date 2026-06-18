#!/usr/bin/env bash
#
# Start the Qdrant + Ollama stack, fully driven by config.toml.
#
# Reads the resolved settings (ports, and whether GPU acceleration is on) from
# the single source of truth and starts docker compose accordingly. GPU is
# enabled when the config's `gpu` flag is true — e.g. environment = "local-cuda".
# There is no separate GPU compose file: the device reservation is injected here.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"

# Pick a Python that can import the package: bundle venv, repo venv, or system.
PY="python3"
for candidate in "$HERE/.venv/bin/python" "$ROOT/.venv/bin/python"; do
  [ -x "$candidate" ] && PY="$candidate" && break
done

# Locate config.toml: explicit env var, then bundle dir, then repo root.
if [ -z "${DFFRNT_CONFIG:-}" ]; then
  for candidate in "$HERE/config.toml" "$ROOT/config.toml"; do
    [ -f "$candidate" ] && DFFRNT_CONFIG="$candidate" && break
  done
fi
export DFFRNT_CONFIG="${DFFRNT_CONFIG:-}"

# Resolve settings through the package (honours env > config.toml > defaults).
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

COMPOSE=(docker compose -f "$HERE/docker-compose.yml")

if [ "$GPU" = "1" ]; then
  echo ">> GPU acceleration ON (from config.toml) — ollama:$OLLAMA_PORT qdrant:$QDRANT_PORT"
  # Inject the GPU reservation via a stdin override so there is a single compose file.
  printf 'services:\n  ollama:\n    gpus: all\n' | "${COMPOSE[@]}" -f - up -d
else
  echo ">> CPU mode (from config.toml) — ollama:$OLLAMA_PORT qdrant:$QDRANT_PORT"
  "${COMPOSE[@]}" up -d
fi

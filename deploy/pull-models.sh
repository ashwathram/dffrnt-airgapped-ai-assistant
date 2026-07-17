#!/usr/bin/env bash
#
# Dev helper: pull whatever llm_model/embed_model config.toml currently
# specifies into the dev Ollama container (started by start.sh). Reads the
# live config instead of hardcoding model names, so this never drifts from
# whatever the operator has actually configured.
#
# Usage: deploy/pull-models.sh
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"

CONFIG="${DFFRNT_CONFIG:-$ROOT/config.toml}"
[ -f "$CONFIG" ] || CONFIG="$ROOT/config.toml.example"

# Read a top-level scalar from config.toml (mirrors dffrnt_ctrl_panel.sh's cfg()).
cfg() {
  local v
  v=$(grep -E "^[[:space:]]*$1[[:space:]]*=" "$CONFIG" 2>/dev/null | head -1 \
      | sed -E 's/^[^=]*=[[:space:]]*//; s/[[:space:]]*#.*$//; s/^"//; s/"$//')
  [ -n "$v" ] && printf '%s' "$v" || printf '%s' "$2"
}

LLM_MODEL="$(cfg llm_model qwen3:14b)"
EMBED_MODEL="$(cfg embed_model bge-m3)"

echo ">> Pulling models from $(basename "$CONFIG"): $LLM_MODEL, $EMBED_MODEL"
docker exec ollama ollama pull "$LLM_MODEL"
docker exec ollama ollama pull "$EMBED_MODEL"

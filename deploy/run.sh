#!/usr/bin/env bash
#
# Runner — manage the deployed app's runtime (mirrors the VS Code start/launch tasks).
#
# Lives in the bundle and, after install, in the app root. The app runs as a
# container, so this needs only Docker. It reads ports + GPU from config.toml,
# manages the Qdrant + Ollama + API containers, pulls models for online builds,
# and prunes any cached model config.toml no longer references (so switching
# llm_model/embed_model + restart reclaims the old model's disk usage).
#
# Usage:
#   ./run.sh start      bring the whole stack up (pull models if online)
#   ./run.sh stop       stop all containers
#   ./run.sh restart    stop then start
#   ./run.sh status     show container + API health
#   ./run.sh logs [svc] follow logs (qdrant|ollama|api; default all)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CMD="${1:-start}"; shift || true

# Bundle manifest (TARGET_SYSTEM, MODELS); absent in a bare dev checkout.
TARGET_SYSTEM="online"; MODELS=""
[ -f "$HERE/bundle.conf" ] && . "$HERE/bundle.conf"

CONFIG="${DFFRNT_CONFIG:-$HERE/config.toml}"
[ -f "$CONFIG" ] || CONFIG="$HERE/../config.toml"

# Read a top-level scalar from config.toml (no host Python needed).
cfg() {
  local v
  v=$(grep -E "^[[:space:]]*$1[[:space:]]*=" "$CONFIG" 2>/dev/null | head -1 \
      | sed -E 's/^[^=]*=[[:space:]]*//; s/[[:space:]]*#.*$//; s/^"//; s/"$//')
  [ -n "$v" ] && printf '%s' "$v" || printf '%s' "$2"
}

API_PORT="$(cfg api_port 8000)"
OLLAMA_URL="$(cfg ollama_url http://localhost:11434)"; OLLAMA_PORT="${OLLAMA_URL##*:}"
QDRANT_URL="$(cfg qdrant_url http://localhost:6333)";  QDRANT_PORT="${QDRANT_URL##*:}"
ENVIRONMENT="$(cfg environment aws)"
GPU="0"; { [ "$(cfg gpu false)" = "true" ] || [ "$ENVIRONMENT" = "local-cuda" ]; } && GPU="1"

# Models the runtime needs: those frozen into the bundle at package time, PLUS
# whatever the live config.toml points at now. Without the latter, editing
# llm_model/embed_model and restarting would run against a model Ollama never
# pulled. Union + de-dupe, preserving order and dropping blanks.
MODELS="$(printf '%s\n' $MODELS "$(cfg llm_model '')" "$(cfg embed_model '')" \
          | awk 'NF && !seen[$0]++' | paste -sd' ' -)"

export API_PORT OLLAMA_PORT QDRANT_PORT
export HOST_CONFIG="$CONFIG"           # mounted into the API container by compose

COMPOSE=(docker compose -f "$HERE/docker-compose.yml" --profile prod)

compose_up() {
  mkdir -p "$HERE/data" "$HERE/logs"
  if [ "$GPU" = "1" ]; then
    echo ">> GPU mode — api:$API_PORT ollama:$OLLAMA_PORT qdrant:$QDRANT_PORT"
    printf 'services:\n  ollama:\n    gpus: all\n' | "${COMPOSE[@]}" -f - up -d
  else
    echo ">> CPU mode — api:$API_PORT ollama:$OLLAMA_PORT qdrant:$QDRANT_PORT"
    "${COMPOSE[@]}" up -d
  fi
}

wait_for() {  # wait_for <label> <url> <max_seconds>
  echo -n ">> Waiting for $1"
  local i=0
  until curl -sf "$2" >/dev/null 2>&1; do
    i=$((i + 1)); [ "$i" -ge "$3" ] && { echo " timeout"; return 1; }
    echo -n "."; sleep 1
  done
  echo " ready"
}

ensure_models() {
  local cached
  cached="$(docker exec ollama ollama list 2>/dev/null || true)"
  for m in $MODELS; do
    # Match the tag literally; Ollama lists an untagged name as "<name>:latest".
    if printf '%s\n' "$cached" | grep -Fq "$m"; then
      continue
    fi
    if [ "$TARGET_SYSTEM" = offline ]; then
      echo "!! Model '$m' missing from the cached store" >&2
    else
      echo ">> Pulling model: $m (not in local cache)"
      docker exec ollama ollama pull "$m"
    fi
  done
}

# Sweep any cached model the LIVE config no longer references (deliberately
# not $MODELS, which also unions in whatever was frozen into the bundle at
# package time) — so switching llm_model/embed_model in config.toml and
# restarting reclaims the old model's blobs from ./ollama_models instead of
# accumulating every model ever used across the deployment's lifetime.
prune_models() {
  local keep="" m name cached
  for m in "$(cfg llm_model '')" "$(cfg embed_model '')"; do
    [ -n "$m" ] || continue
    case "$m" in *:*) keep="$keep $m" ;; *) keep="$keep $m:latest" ;; esac
  done
  [ -n "$keep" ] || return 0
  cached="$(docker exec ollama ollama list 2>/dev/null | tail -n +2 | awk '{print $1}')"
  for name in $cached; do
    [ -n "$name" ] || continue
    case " $keep " in
      *" $name "*) ;;
      *) echo ">> Removing cached model no longer in use: $name"
         docker exec ollama ollama rm "$name" >/dev/null || true ;;
    esac
  done
}

case "$CMD" in
  start)
    compose_up
    wait_for "Qdrant" "http://localhost:$QDRANT_PORT/healthz" 120
    wait_for "Ollama" "http://localhost:$OLLAMA_PORT"          120
    ensure_models
    prune_models
    wait_for "API"    "http://localhost:$API_PORT/health"      120 || \
      echo "   (API not healthy yet — it restarts automatically; check ./run.sh logs api)"
    echo ">> Up. UI: http://localhost:$API_PORT"
    ;;
  stop)
    echo ">> Stopping containers"
    "${COMPOSE[@]}" down
    ;;
  restart)
    "$HERE/run.sh" stop || true
    exec "$HERE/run.sh" start
    ;;
  status)
    "${COMPOSE[@]}" ps
    if curl -sf -o /dev/null "http://localhost:$API_PORT/health"; then
      echo "API: up   (http://localhost:$API_PORT)"
    else
      echo "API: down (start with ./run.sh start)"
    fi
    ;;
  logs)
    "${COMPOSE[@]}" logs -f "$@"
    ;;
  *) echo "Usage: ./run.sh {start|stop|restart|status|logs}" >&2; exit 2 ;;
esac

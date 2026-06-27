#!/usr/bin/env bash
#
# Packager — build a self-contained deployment bundle (containerized).
#
# The app ships as a Docker image, so the target needs only Docker — no Python,
# uv or pip. Produces THREE files in the output dir and nothing else:
#   <name>.tar.gz   the bundle (app image + runner + compose + config; plus the
#                   Qdrant/Ollama images and the Ollama model store for OFFLINE)
#   install.sh      the single installer (deploys straight from the tarball)
#   README.md       install + run instructions
#
# Run on a NETWORKED machine whose OS/arch matches the target.
#
# Usage:
#   deploy/package.sh <models_dir> <TARGET_SYSTEM>
#   deploy/package.sh OLLAMA_MODELS_DIR=~/.ollama/models TARGET_SYSTEM=AWS
#
#   <models_dir>     cached Ollama model store (required for OFFLINE; ignored for AWS)
#   <TARGET_SYSTEM>  OFFLINE  -> cache everything (app + base images + models) for
#                               an air-gapped box
#                    AWS      -> online target; only the app image is bundled, and
#                               the installer pulls the base images + models at
#                               deploy time to keep the tarball small
#
# Env: APP_IMAGE (default dffrnt-assistant:latest), OUT_DIR (default <repo>/dist)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# ---- parse args (positional or KEY=VALUE, in any order) ---------------------
MODELS_DIR="" ; TARGET=""
for arg in "$@"; do
  case "$arg" in
    TARGET[-_]SYSTEM=*|TARGET=*) TARGET="${arg#*=}" ;;
    OLLAMA_MODELS_DIR=*|MODELS[-_]DIR=*|MODELS=*) MODELS_DIR="${arg#*=}" ;;
    *) if   [ -z "$MODELS_DIR" ]; then MODELS_DIR="$arg"
       elif [ -z "$TARGET" ];     then TARGET="$arg"
       fi ;;
  esac
done
MODELS_DIR="${MODELS_DIR:-${OLLAMA_MODELS_DIR:-$HOME/.ollama/models}}"
TARGET="${TARGET:-${TARGET_SYSTEM:-OFFLINE}}"

case "$(printf '%s' "$TARGET" | tr '[:lower:]' '[:upper:]')" in
  OFFLINE|AIRGAP|AIRGAPPED) MODE="offline" ;;
  AWS|ONLINE|CLOUD)         MODE="online"  ;;
  *) echo "!! Unknown TARGET_SYSTEM '$TARGET' (use OFFLINE or AWS)" >&2; exit 2 ;;
esac

APP_IMAGE="${APP_IMAGE:-dffrnt-assistant:latest}"
OUT="${OUT_DIR:-$ROOT/dist}"
NAME="dffrnt-$([ "$MODE" = offline ] && echo offline || echo aws)"
STAGE="$OUT/.stage/dffrnt"

echo ">> Packaging '$NAME' ($MODE)"

# ---- model names the target will need (from the bundled config) -------------
read -r LLM_MODEL EMBED_MODEL < <(python3 - "$ROOT/config.toml.example" <<'PY'
import sys, tomllib
with open(sys.argv[1], "rb") as f: c = tomllib.load(f)
print(c.get("llm_model", ""), c.get("embed_model", ""))
PY
)
MODELS="$(echo "$LLM_MODEL $EMBED_MODEL" | xargs)"
[ -n "$MODELS" ] || { echo "!! Could not read models from config.toml.example" >&2; exit 1; }
echo ">> Models for target: $MODELS"

# ---- fresh staging tree ----------------------------------------------------
rm -rf "$OUT"
mkdir -p "$STAGE/images"

echo ">> [1/3] Building the application image ($APP_IMAGE)"
docker build -t "$APP_IMAGE" -f "$ROOT/deploy/Dockerfile" "$ROOT"

echo ">> [2/3] Saving images"
# The app image is custom (not on a public registry), so it ships in every build.
docker save "$APP_IMAGE" -o "$STAGE/images/app.tar"
if [ "$MODE" = offline ]; then
  for image in qdrant/qdrant ollama/ollama; do
    docker pull "$image"
    docker save "$image" -o "$STAGE/images/$(echo "$image" | tr '/:' '__').tar"
  done
else
  echo "   (online — Qdrant/Ollama base images pulled at deploy time)"
fi

echo ">> [3/3] Bundling models + runtime files"
if [ "$MODE" = offline ]; then
  [ -d "$MODELS_DIR" ] || { echo "!! $MODELS_DIR not found — pull models first (ollama pull $MODELS)" >&2; exit 1; }
  mkdir -p "$STAGE/ollama_models"
  cp -a "$MODELS_DIR/." "$STAGE/ollama_models/"
else
  echo "   (online — models pulled at deploy time: $MODELS)"
fi

cp "$ROOT/deploy/docker-compose.yml" "$ROOT/deploy/run.sh" "$STAGE/"
chmod +x "$STAGE/run.sh"
cp "$ROOT/config.toml.example" "$STAGE/config.toml"
cat > "$STAGE/bundle.conf" <<EOF
TARGET_SYSTEM=$MODE
MODELS="$MODELS"
APP_IMAGE=$APP_IMAGE
EOF

# ---- assemble the three deliverables ---------------------------------------
mkdir -p "$OUT"
tar -czf "$OUT/$NAME.tar.gz" -C "$OUT/.stage" dffrnt
cp "$ROOT/deploy/install.sh" "$OUT/install.sh"
chmod +x "$OUT/install.sh"
sed "s/@NAME@/$NAME/g; s/@MODE@/$MODE/g; s/@MODELS@/$MODELS/g" \
  "$ROOT/deploy/README.target.md" > "$OUT/README.md"

rm -rf "$OUT/.stage"
echo ">> Done. $OUT now contains:"
ls -1 "$OUT"

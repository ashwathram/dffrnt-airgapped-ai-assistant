#!/usr/bin/env bash
#
# Build a self-contained offline bundle: Python wheels + container images +
# Ollama models + this app. Run on a NETWORKED machine whose OS/arch matches the
# air-gapped target (e.g. macOS arm64 for the Mac Studio). Produces a tarball you
# copy to the target and unpack with install_offline.sh.
#
# Usage:  deploy/build_offline.sh [output_dir]
# Env:    TARGET_PYTHON (default 3.14), OLLAMA_MODELS_DIR (default ~/.ollama/models)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-$ROOT/dist/offline-bundle}"
PYVER="${TARGET_PYTHON:-3.14}"
MODELS_DIR="${OLLAMA_MODELS_DIR:-$HOME/.ollama/models}"

mkdir -p "$OUT/wheelhouse" "$OUT/images" "$OUT/ollama_models"
echo ">> Building offline bundle in $OUT (Python $PYVER)"

echo ">> [1/5] Exporting locked requirements"
cd "$ROOT"
if command -v uv >/dev/null 2>&1; then
  uv export --no-dev --no-emit-project --format requirements-txt > "$OUT/requirements.txt"
else
  python - "$ROOT/pyproject.toml" > "$OUT/requirements.txt" <<'PY'
import sys, tomllib
with open(sys.argv[1], "rb") as f:
    print("\n".join(tomllib.load(f)["project"]["dependencies"]))
PY
fi

echo ">> [2/5] Downloading dependency wheels"
# IMPORTANT: cp$PYVER wheels for the target arch must exist. If pip can't find a
# wheel it fails here (on the networked machine) rather than on the air-gapped box.
if ! pip download -r "$OUT/requirements.txt" -d "$OUT/wheelhouse" \
      --only-binary=:all: --python-version "$PYVER"; then
  echo "!! A wheel is unavailable for cp$PYVER on this platform." >&2
  echo "   Re-run on a machine matching the target arch, or pin Python lower in pyproject.toml." >&2
  exit 1
fi

echo ">> [3/5] Building the application wheel"
pip wheel "$ROOT" -w "$OUT/wheelhouse" --no-deps

echo ">> [4/5] Saving container images"
for image in qdrant/qdrant ollama/ollama; do
  docker pull "$image"
  docker save "$image" -o "$OUT/images/$(echo "$image" | tr '/:' '__').tar"
done

echo ">> [5/5] Exporting Ollama models from $MODELS_DIR"
if [ -d "$MODELS_DIR" ]; then
  cp -a "$MODELS_DIR/." "$OUT/ollama_models/"
else
  echo "!! $MODELS_DIR not found. Pull the models first, e.g.:" >&2
  echo "     ollama pull qwen2.5:7b && ollama pull nomic-embed-text" >&2
  exit 1
fi

cp "$ROOT/deploy/docker-compose.yml" "$ROOT/deploy/install_offline.sh" "$ROOT/deploy/start.sh" "$OUT/"
chmod +x "$OUT/install_offline.sh" "$OUT/start.sh"
cp "$ROOT/config.toml.example" "$OUT/config.toml"

tar -czf "$OUT.tar.gz" -C "$(dirname "$OUT")" "$(basename "$OUT")"
echo ">> Bundle ready: $OUT.tar.gz"

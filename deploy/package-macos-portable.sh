#!/usr/bin/env bash
#
# package-macos-portable.sh — fetch the portable macOS runtime into dist/.
#
# The macOS (portable) pathway ships Ollama as a NATIVE host binary (Metal
# acceleration is automatic on Apple Silicon — keeping it out of the Docker VM
# is the entirety of enabling Metal) and runs Qdrant + the API as containers
# under colima. This script downloads those pinned artifacts on a NETWORKED
# build machine and stages them as:
#
#   dist/portable/macos/
#     bin/ollama            native Ollama server+CLI (universal binary)
#     bin/colima            container runtime frontend (Apple Virtualization.framework)
#     bin/limactl           colima's VM engine
#     share/lima/…          lima guest agents (resolved relative to bin/limactl)
#     bin/docker            static docker CLI (client only — the daemon lives in the VM)
#     bin/docker-compose    compose v2 CLI plugin
#     python/…              relocatable CPython (runs the control panel; no Tk needed)
#     VERSIONS              what was fetched, for the audit trail
#
# It ALSO stages the manager itself into dist/ (steps 6-7), so the whole macOS
# deliverable comes from this one script after package.sh:
#     dist/installer/         the manager source (run by the vendored python)
#     dist/dffrnt-manager     shell launcher -> vendored python (replaces the
#                             Linux ELF package.sh emits, which can't run on Mac)
#
# The portable installer copies portable/macos + the source + a launcher into
# <install>/ so the install self-manages; ALL runtime state
# (COLIMA_HOME/LIMA_HOME/DOCKER_CONFIG) stays under <install>/portable.
#
# Run AFTER package.sh (which wipes dist/).
#
# AIR-GAP CAVEAT (deliberate, documented, unsolved here): colima's first
# `colima start` downloads its guest Linux image. For a truly offline target,
# warm the cache once on a NETWORKED Mac (run `colima start` under
# COLIMA_HOME/LIMA_HOME pointed at this tree) before transferring dist/ —
# or accept one-time network access at install. Everything else (models,
# images, binaries) is fully offline.
#
# Usage: deploy/package-macos-portable.sh [ARCH]   (arm64 [default] | x86_64)
# Env:   OUT_DIR (default <repo>/dist), and *_VERSION overrides below.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST="${OUT_DIR:-$ROOT/dist}"
OUT="$DIST/portable/macos"
ARCH="${1:-arm64}"   # arm64 (Apple Silicon) | x86_64 (Intel, CPU-only inference)

# ---- version pins (bump deliberately; a 404 below means a pin moved) --------
# OLLAMA_VERSION tracks the ollama/ollama image pin in docker-compose.yml so
# native macOS inference runs the same engine the Linux containers do.
OLLAMA_VERSION="${OLLAMA_VERSION:-v0.32.1}"
COLIMA_VERSION="${COLIMA_VERSION:-v0.8.1}"
LIMA_VERSION="${LIMA_VERSION:-1.0.7}"
DOCKER_CLI_VERSION="${DOCKER_CLI_VERSION:-28.3.2}"
COMPOSE_VERSION="${COMPOSE_VERSION:-v2.39.1}"
# Relocatable CPython for the control panel (installer/ runs from source on
# macOS: modern macOS ships NO system python, and the manager can't be
# PyInstaller-frozen for a Mac from a Linux build box). python-build-standalone
# publishes self-contained darwin builds — fetched here exactly like the other
# mac-native binaries, no Mac needed to package. The panel UI is the browser,
# so this Python needs no Tk. Match PYTHON_VERSION to pyproject's floor (3.14).
PYTHON_VERSION="${PYTHON_VERSION:-3.14.6}"
PBS_RELEASE="${PBS_RELEASE:-20260718}"

case "$ARCH" in
  arm64)  LIMA_ARCH="arm64";  DOCKER_ARCH="aarch64"; COMPOSE_ARCH="aarch64"; COLIMA_ARCH="arm64" ;;
  x86_64) LIMA_ARCH="x86_64"; DOCKER_ARCH="x86_64";  COMPOSE_ARCH="x86_64";  COLIMA_ARCH="x86_64" ;;
  *) echo "!! ARCH must be arm64 or x86_64 (got '$ARCH')" >&2; exit 2 ;;
esac

command -v curl >/dev/null || { echo "!! curl is required" >&2; exit 1; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$OUT/bin"

fetch() { # fetch <url> <dest-file>
  echo "   $1"
  curl -fSL --progress-bar "$1" -o "$2"
}

echo ">> [1/7] Ollama $OLLAMA_VERSION (native — Metal automatic on Apple Silicon)"
fetch "https://github.com/ollama/ollama/releases/download/${OLLAMA_VERSION}/ollama-darwin.tgz" \
      "$WORK/ollama.tgz"
tar -xzf "$WORK/ollama.tgz" -C "$WORK"
# The tgz contains the `ollama` binary at its top level (universal: arm64+x86_64).
mv "$WORK/ollama" "$OUT/bin/ollama"

echo ">> [2/7] colima $COLIMA_VERSION (portable container runtime)"
fetch "https://github.com/abiosoft/colima/releases/download/${COLIMA_VERSION}/colima-Darwin-${COLIMA_ARCH}" \
      "$OUT/bin/colima"

echo ">> [3/7] lima $LIMA_VERSION (colima's VM engine + guest agents)"
fetch "https://github.com/lima-vm/lima/releases/download/v${LIMA_VERSION}/lima-${LIMA_VERSION}-Darwin-${LIMA_ARCH}.tar.gz" \
      "$WORK/lima.tgz"
# Extract the whole tree: bin/limactl finds share/lima relative to itself.
mkdir -p "$WORK/lima-tree"
tar -xzf "$WORK/lima.tgz" -C "$WORK/lima-tree"
cp -a "$WORK/lima-tree/bin/." "$OUT/bin/"
mkdir -p "$OUT/share"
cp -a "$WORK/lima-tree/share/." "$OUT/share/"

echo ">> [4/7] docker CLI $DOCKER_CLI_VERSION (static client) + compose $COMPOSE_VERSION"
fetch "https://download.docker.com/mac/static/stable/${DOCKER_ARCH}/docker-${DOCKER_CLI_VERSION}.tgz" \
      "$WORK/docker.tgz"
tar -xzf "$WORK/docker.tgz" -C "$WORK"     # extracts docker/docker
mv "$WORK/docker/docker" "$OUT/bin/docker"
fetch "https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-darwin-${COMPOSE_ARCH}" \
      "$OUT/bin/docker-compose"

echo ">> [5/7] CPython $PYTHON_VERSION (relocatable, for the control panel)"
case "$ARCH" in
  arm64)  PBS_ARCH="aarch64-apple-darwin" ;;
  x86_64) PBS_ARCH="x86_64-apple-darwin" ;;
esac
fetch "https://github.com/astral-sh/python-build-standalone/releases/download/${PBS_RELEASE}/cpython-${PYTHON_VERSION}+${PBS_RELEASE}-${PBS_ARCH}-install_only.tar.gz" \
      "$WORK/python.tgz"
# Extracts a self-contained python/ tree (bin/python3, lib/...) that runs the
# manager on the target — no host Python, no Tk (the panel UI is the browser).
tar -xzf "$WORK/python.tgz" -C "$OUT"

echo ">> [6/7] Manager source + macOS launcher (dist/)"
# macOS runs the manager from SOURCE on the vendored python — a Linux-frozen
# binary can't execute on a Mac. Ship the source next to the bundle and drop a
# shell launcher that wraps the vendored interpreter, OVERWRITING the Linux ELF
# package.sh left in dist/. install() re-stages both into the install dir so it
# self-manages afterwards (installer/installers/portable_installer.py).
rm -rf "$DIST/installer"
cp -R "$ROOT/installer" "$DIST/installer"
find "$DIST/installer" -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
cat > "$DIST/dffrnt-manager" <<'LAUNCH'
#!/bin/sh
# DFFRNT control panel (macOS, pre-install bootstrap) — runs the vendored
# CPython against the manager source shipped alongside. No arguments = browser
# panel (use the Install tab); any command = headless CLI (e.g. install).
HERE="$(cd "$(dirname "$0")" && pwd)"
exec env PYTHONPATH="$HERE" "$HERE/portable/macos/python/bin/python3" -m installer "$@"
LAUNCH
chmod +x "$DIST/dffrnt-manager"

echo ">> [7/7] Permissions + manifest"
chmod +x "$OUT"/bin/*
cat > "$OUT/VERSIONS" <<EOF
arch=$ARCH
ollama=$OLLAMA_VERSION
colima=$COLIMA_VERSION
lima=$LIMA_VERSION
docker_cli=$DOCKER_CLI_VERSION
compose=$COMPOSE_VERSION
python=$PYTHON_VERSION+$PBS_RELEASE
fetched=$(date -u +%Y-%m-%dT%H:%M:%SZ)
EOF

echo ">> Done. Portable macOS runtime staged in $OUT"
echo "   Bootstrap: cd $DIST && ./dffrnt-manager   (Install tab, or: install)"
ls -1 "$OUT/bin"
echo
echo "   REMINDER (air-gapped targets): colima's first start downloads its guest"
echo "   image — warm it on a networked Mac before transfer, or allow one-time"
echo "   network access at install. See the header of this script."

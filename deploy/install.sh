#!/usr/bin/env bash
#
# Installer — deploy the application straight from the bundle tarball.
#
# The app runs as a container, so the target needs only Docker — no Python, uv or
# pip. Place this next to the single dffrnt-*.tar.gz from package.sh and run it.
# It checks prerequisites, unpacks the bundle, loads the container image(s), and
# brings the stack up (pulling base images/models for online builds).
#
# Usage:  ./install.sh [install_dir]        (default: ./dffrnt)
# Env:    BUNDLE=<path/to/tarball>          (auto-detected if omitted)
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="$(cd "$(dirname "${1:-$HERE/dffrnt}")" 2>/dev/null && pwd)/$(basename "${1:-dffrnt}")"

# ---- locate the bundle ------------------------------------------------------
BUNDLE="${BUNDLE:-}"
if [ -z "$BUNDLE" ]; then
  shopt -s nullglob
  cands=("$HERE"/dffrnt-*.tar.gz)
  shopt -u nullglob
  [ "${#cands[@]}" -eq 1 ] || { echo "!! Expected exactly one dffrnt-*.tar.gz next to install.sh (found ${#cands[@]}). Set BUNDLE=<path>." >&2; exit 1; }
  BUNDLE="${cands[0]}"
fi
[ -f "$BUNDLE" ] || { echo "!! Bundle not found: $BUNDLE" >&2; exit 1; }
echo ">> Installing from $(basename "$BUNDLE") into $DEST"

# ---- prerequisite checks (collect everything, then report) ------------------
MISSING=0
have() { command -v "$1" >/dev/null 2>&1; }
fail() { echo "   [MISSING] $1" >&2; echo "             $2" >&2; MISSING=1; }

echo ">> [1/4] Checking prerequisites"
have tar  || fail "tar"  "install your distro's 'tar' package"
have curl || fail "curl" "install 'curl' (used for health checks)"
if have docker; then
  docker info >/dev/null 2>&1 || fail "docker daemon" "Docker is installed but not running — start it (e.g. 'systemctl start docker') and ensure your user can access it"
  docker compose version >/dev/null 2>&1 || fail "docker compose" "install the Docker Compose v2 plugin"
else
  fail "docker" "install Docker Engine + the Compose v2 plugin (https://docs.docker.com/engine/install/)"
fi
[ "$MISSING" -eq 0 ] || { echo "!! Missing prerequisites (see above). Install them and re-run." >&2; exit 1; }

# ---- update handling: stop the old stack, decide the config's fate ----------
# All no-ops on a fresh install. On an update we stop the running stack before
# swapping the image, and protect the operator's edited config.toml — the bundle
# ships a default config.toml that the untar below would otherwise clobber.
KEEP_CONFIG=0
# The control panel was named run.sh before; fall back to it so updates from an
# older install still stop the running stack before the image is swapped.
CTRL="$DEST/dffrnt_ctrl_panel.sh"; [ -f "$CTRL" ] || CTRL="$DEST/run.sh"
if [ -f "$CTRL" ]; then
  echo ">> Updating an existing install in $DEST — stopping the running stack first"
  bash "$CTRL" stop || true
fi
if [ -f "$DEST/config.toml" ]; then
  ans="${OVERWRITE_CONFIG:-}"               # set OVERWRITE_CONFIG=y|n to skip the prompt
  if [ -z "$ans" ]; then
    if [ -t 0 ]; then
      printf '>> Existing config.toml found. Overwrite it with the bundle default? [y/N] '
      read -r ans || ans=""
    else
      ans="n"                               # non-interactive: keep it (the safe default)
    fi
  fi
  case "$ans" in
    [yY]|[yY][eE][sS])
      echo "   overwriting — archiving the current config as config.toml.old"
      cp -a "$DEST/config.toml" "$DEST/config.toml.old"
      ;;
    *)
      echo "   keeping the existing config.toml"
      KEEP_CONFIG=1
      cp -a "$DEST/config.toml" "$DEST/.config.toml.keep"
      ;;
  esac
fi

# ---- unpack -----------------------------------------------------------------
echo ">> [2/4] Unpacking bundle"
mkdir -p "$DEST"
tar -xzf "$BUNDLE" -C "$DEST" --strip-components=1
# Restore the preserved config over the bundle's default (kept across the update).
[ "$KEEP_CONFIG" -eq 1 ] && mv -f "$DEST/.config.toml.keep" "$DEST/config.toml"
# shellcheck source=/dev/null
. "$DEST/bundle.conf"   # TARGET_SYSTEM, MODELS, APP_IMAGE

# ---- load container image(s) ------------------------------------------------
echo ">> [3/4] Loading container image(s)"
for t in "$DEST"/images/*.tar; do docker load -i "$t"; done

# ---- bring the stack up (pulls base images + models for online) ------------
echo ">> [4/4] Starting the stack"
bash "$DEST/dffrnt_ctrl_panel.sh" start

cat <<EOF

>> Installed ($TARGET_SYSTEM). The app lives in: $DEST

   Manage it:  cd "$DEST"
               ./dffrnt_ctrl_panel.sh          # interactive menu
               ./dffrnt_ctrl_panel.sh status | stop | restart | logs | reingest
   UI:         http://localhost:8000
EOF

#!/usr/bin/env bash
#
# Install the offline bundle on the air-gapped target. Run from inside the
# unpacked bundle directory (the one containing wheelhouse/, images/, etc.).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo ">> [1/3] Creating virtualenv and installing from the wheelhouse"
python3 -m venv "$HERE/.venv"
"$HERE/.venv/bin/pip" install --no-index --find-links "$HERE/wheelhouse" \
  dffrnt-airgapped-ai-assistant

echo ">> [2/3] Loading container images"
for tarball in "$HERE"/images/*.tar; do
  docker load -i "$tarball"
done

echo ">> [3/3] Done."
cat <<EOF

Next steps (offline):
  1. Start services:   "$HERE/start.sh"   (config-driven; GPU if config.toml enables it)
  2. Run the API:      DFFRNT_CONFIG="$HERE/config.toml" "$HERE/.venv/bin/dffrnt-api"
  3. Batch-ingest:     DFFRNT_CONFIG="$HERE/config.toml" "$HERE/.venv/bin/dffrnt-ingest" --source-root <docs>
  4. Open the UI:      http://localhost:8000
EOF

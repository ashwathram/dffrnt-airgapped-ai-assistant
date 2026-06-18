import sys
from pathlib import Path

# Make the in-tree package importable without an editable install. Useful for
# air-gapped development and for running unit tests before `uv sync` has run.
sys.path.insert(0, str(Path(__file__).resolve().parent))

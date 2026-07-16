import sys
from pathlib import Path

# Make the in-tree package importable without an editable install.
sys.path.insert(0, str(Path(__file__).resolve().parent))


def pytest_addoption(parser):
    parser.addoption(
        "--reset-corpus", action="store_true", default=False,
        help="wipe the document/summary collections and re-ingest tests/eval/corpus "
             "before running the evaluation suite (destructive)",
    )

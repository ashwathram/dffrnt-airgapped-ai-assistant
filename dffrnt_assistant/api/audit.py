"""Append-only JSONL audit log."""

import json
from datetime import datetime, timezone
from pathlib import Path


class AuditLog:
    """Appends timestamped events (uploads, queries, deletions, perf timings)
    to a JSONL file."""

    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event_type: str, data: dict) -> None:
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            **data,
        }
        with self.path.open("a") as fh:
            fh.write(json.dumps(event) + "\n")

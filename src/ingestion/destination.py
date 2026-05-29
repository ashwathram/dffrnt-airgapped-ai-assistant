from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

_SLUG_RE = re.compile(r"[^a-z0-9_]+")


def _slugify(value: str) -> str:
    v = str(value or "").lower().strip()
    v = v.replace(" ", "_")
    v = _SLUG_RE.sub("", v)
    return v or "default"


def make_collection_name(
    workspace: Optional[str], schema: Optional[str], base_name: Optional[str] = None
) -> str:
    parts = ["ingest"]
    if workspace:
        parts.append(_slugify(workspace))
    if schema:
        parts.append(_slugify(schema))
    if base_name:
        parts.append(_slugify(base_name))
    parts.append(datetime.utcnow().strftime("%Y%m%d%H%M%S"))
    return "_".join(parts)

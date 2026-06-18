"""Load and validate sidecar metadata for batch ingestion.

Supported input formats: JSON and CSV/TSV. Returns a mapping keyed by filename
and absolute path to a compact dict with normalized keys: ``document_type``,
``department``, ``client_project``, ``tags``, ``tag_paths``.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict

from .tags import normalize_tag_payload

ALLOWED_FIELDS = {"document_type", "department", "client_project", "tags", "tag_paths"}


def _normalize_value(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def _normalize_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, val in entry.items():
        nk = k.strip()
        if nk in {"tags", "tag_paths"}:
            continue
        if nk in ALLOWED_FIELDS:
            nv = _normalize_value(val)
            if nv is not None:
                out[nk] = nv

    leaf_tags, expanded_paths = normalize_tag_payload(entry.get("tags") or entry.get("tag_paths"))
    if leaf_tags:
        out["tags"] = leaf_tags
    if expanded_paths:
        out["tag_paths"] = expanded_paths

    raw_tag_paths = entry.get("tag_paths")
    if raw_tag_paths:
        _, explicit_paths = normalize_tag_payload(raw_tag_paths)
        if explicit_paths:
            out["tag_paths"] = list(dict.fromkeys((out.get("tag_paths") or []) + explicit_paths))
    return out


def load_metadata_map(path: Path) -> Dict[str, Dict[str, Any]]:
    """Load a metadata mapping from a JSON or CSV/TSV sidecar."""
    if not path or not path.exists():
        return {}

    mapping: Dict[str, Any] = {}
    try:
        if path.suffix.lower() in {".csv", ".tsv"}:
            delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
            with path.open("r", encoding="utf-8") as fh:
                for row in csv.DictReader(fh, delimiter=delimiter):
                    key = row.get("filename") or row.get("file") or row.get("path") or row.get("name")
                    if key:
                        mapping[key] = {k: v for k, v in row.items() if k}
        else:
            mapping = json.loads(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}

    normalized: Dict[str, Dict[str, Any]] = {}
    for key, entry in mapping.items():
        if not isinstance(entry, dict):
            continue
        compact = _normalize_entry(entry)
        if not compact:
            continue
        normalized[str(key)] = compact
        normalized[Path(str(key)).name] = compact
        try:
            normalized[str((Path.cwd() / str(key)).resolve())] = compact
        except Exception:
            pass

    return normalized

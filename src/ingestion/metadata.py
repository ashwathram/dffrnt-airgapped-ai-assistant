"""Load and validate sidecar metadata for ingestion.

Supported input formats: JSON and CSV/TSV. Returns a mapping keyed by
filename and absolute path to a compact dict with normalized keys:
`document_type`, `department`, `client_project`, `tags`, `tag_paths`.
"""

from __future__ import annotations

import json
import csv
from pathlib import Path
from typing import Dict, Any

from ingestion.tags import normalize_tag_payload

ALLOWED_FIELDS = {"document_type", "department", "client_project", "tags", "tag_paths"}


def _normalize_value(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def _normalize_entry(entry: Dict[str, Any]) -> Dict[str, str]:
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
    """Load metadata mapping from JSON or CSV/TSV sidecar.

    Returns a mapping keyed by both the original key and the filename and
    the resolved absolute path when possible. Values are compact dicts
    containing only allowed fields and normalized string values.
    """
    mapping: Dict[str, Dict[str, Any]] = {}
    if not path or not path.exists():
        return {}

    try:
        if path.suffix.lower() == ".json":
            mapping = json.loads(path.read_text(encoding="utf-8")) or {}
        elif path.suffix.lower() in {".csv", ".tsv"}:
            delim = "\t" if path.suffix.lower() == ".tsv" else ","
            with path.open("r", encoding="utf-8") as fh:
                reader = csv.DictReader(fh, delimiter=delim)
                for r in reader:
                    key = r.get("filename") or r.get("file") or r.get("path") or r.get("name")
                    if not key:
                        continue
                    mapping[key] = {k: v for k, v in r.items() if k}
        else:
            # try JSON fallback
            mapping = json.loads(path.read_text(encoding="utf-8")) or {}
    except Exception:
        try:
            mapping = json.loads(path.read_text(encoding="utf-8")) or {}
        except Exception:
            mapping = {}

    normalized: Dict[str, Dict[str, Any]] = {}
    for key, entry in mapping.items():
        if not isinstance(entry, dict):
            continue
        compact = _normalize_entry(entry)
        if not compact:
            # skip rows with no valid fields
            continue
        # add multiple key forms
        normalized_key = str(key)
        normalized[normalized_key] = compact
        # filename-only
        try:
            fname = Path(normalized_key).name
            normalized[fname] = compact
        except Exception:
            pass
        # absolute resolved path when possible
        try:
            p = (Path.cwd() / normalized_key).resolve()
            normalized[str(p)] = compact
        except Exception:
            pass

    return normalized

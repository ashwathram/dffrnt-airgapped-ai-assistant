"""Helpers for normalizing hierarchical user tags."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from typing import Any

_HIERARCHY_SPLIT_RE = re.compile(r"\s*(?:/|>|\\|\|)\s*")


def _unique_preserve_order(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def _normalize_path_text(value: str) -> str | None:
    text = str(value).strip()
    if not text:
        return None
    parts = [segment.strip() for segment in _HIERARCHY_SPLIT_RE.split(text) if segment.strip()]
    if not parts:
        return None
    return "/".join(parts)


def _coerce_tag_paths(value: Any) -> list[str]:
    if value is None:
        return []

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text.startswith("[") or text.startswith("{"):
            try:
                parsed = json.loads(text)
            except Exception:
                parsed = None
            else:
                return _coerce_tag_paths(parsed)
        normalized = _normalize_path_text(text)
        return [normalized] if normalized else []

    if isinstance(value, dict):
        base = None
        for key in ("path", "tag", "name", "label"):
            candidate = value.get(key)
            if candidate:
                base = _normalize_path_text(candidate)
                if base:
                    break

        children = value.get("children")
        if children:
            child_paths: list[str] = []
            for child in children if isinstance(children, list) else [children]:
                child_paths.extend(_coerce_tag_paths(child))
            if base:
                combined = [base]
                for child_path in child_paths:
                    if child_path == base or child_path.startswith(f"{base}/"):
                        combined.append(child_path)
                    else:
                        combined.append(f"{base}/{child_path}")
                return _unique_preserve_order(combined)
            return _unique_preserve_order(child_paths)

        return [base] if base else []

    if isinstance(value, list):
        flattened: list[str] = []
        for item in value:
            flattened.extend(_coerce_tag_paths(item))
        return _unique_preserve_order(flattened)

    normalized = _normalize_path_text(str(value))
    return [normalized] if normalized else []


def normalize_tag_payload(value: Any) -> tuple[list[str], list[str]]:
    """Return (leaf_tags, expanded_paths) for hierarchical tags."""

    leaf_tags = _unique_preserve_order(_coerce_tag_paths(value))
    expanded_paths: list[str] = []
    for tag_path in leaf_tags:
        segments = [segment for segment in tag_path.split("/") if segment]
        for end in range(1, len(segments) + 1):
            expanded_paths.append("/".join(segments[:end]))
    return leaf_tags, _unique_preserve_order(expanded_paths)

"""Reads config.toml with the precedence the whole app observes: env var
wins, then the file, then a hardcoded default — never an error for a
missing key (mirrors dffrnt_assistant.config.load_settings). Also reads
bundle.conf (the packager's manifest) and performs the one config WRITE in
the codebase (write_config_value, for model switching). Shared by the
management backends, the installer, the GUI, and the CLI.
"""

from __future__ import annotations

import os
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    api_port: int
    ollama_url: str
    qdrant_url: str
    gpu: bool
    llm_model: str
    embed_model: str
    audit_log_path: str

    @property
    def ollama_port(self) -> str:
        return self.ollama_url.rsplit(":", 1)[-1]

    @property
    def qdrant_port(self) -> str:
        return self.qdrant_url.rsplit(":", 1)[-1]


_DEFAULTS = {
    "api_port": 8000,
    "ollama_url": "http://localhost:11434",
    "qdrant_url": "http://localhost:6333",
    "gpu": False,
    "llm_model": "",
    "embed_model": "",
    "audit_log_path": "logs/audit.jsonl",
}


def find_app_root() -> Path:
    """Locates the directory holding docker-compose.yml + config.toml.
    Three layouts are expected:

      dev checkout:  repo/installer/  (this package) + repo/deploy/
      installed bundle: everything (compose file, manager binary, config)
        sits together in one directory
      frozen manager NEXT TO a bundle tarball (pre-install): no compose
        file anywhere yet — the fallback is fine, the Install flow creates
        the app root

    Frozen (PyInstaller) builds must anchor on sys.executable: __file__
    lives in the one-file bundle's temp extraction dir, which is neither
    stable nor next to anything. DFFRNT_APP_ROOT overrides everything,
    mirroring DFFRNT_CONFIG's role for the config file itself.
    """
    env_path = os.environ.get("DFFRNT_APP_ROOT")
    if env_path:
        return Path(env_path)
    if getattr(sys, "frozen", False):
        here = Path(sys.executable).resolve().parent
    else:
        here = Path(__file__).resolve().parent
    for candidate in (here.parent / "deploy", here, here.parent):
        if (candidate / "docker-compose.yml").is_file():
            return candidate
    # Nothing found — fall back to the dev-checkout layout; callers surface
    # a clear error themselves when docker-compose.yml still isn't there.
    return here.parent / "deploy"


def find_config(app_root: Path) -> Path | None:
    """CONFIG resolution: $DFFRNT_CONFIG, else <app_root>/config.toml, else
    <app_root>/../config.toml (bare dev checkout, where deploy/ sits next
    to the repo-root config.toml).
    """
    env_path = os.environ.get("DFFRNT_CONFIG")
    if env_path:
        return Path(env_path)
    candidate = app_root / "config.toml"
    if candidate.is_file():
        return candidate
    parent_candidate = app_root.parent / "config.toml"
    if parent_candidate.is_file():
        return parent_candidate
    return None


def load_config(app_root: Path) -> AppConfig:
    path = find_config(app_root)
    data: dict = {}
    if path and path.is_file():
        with path.open("rb") as f:
            data = tomllib.load(f)

    def get(key: str):
        # env beats file beats default, matching cfg()'s precedence.
        env_val = os.environ.get(key.upper())
        if env_val is not None:
            return env_val
        return data.get(key, _DEFAULTS[key])

    gpu_raw = get("gpu")
    gpu = gpu_raw if isinstance(gpu_raw, bool) else str(gpu_raw).strip().lower() == "true"

    return AppConfig(
        api_port=int(get("api_port")),
        ollama_url=str(get("ollama_url")),
        qdrant_url=str(get("qdrant_url")),
        gpu=gpu,
        llm_model=str(get("llm_model")),
        embed_model=str(get("embed_model")),
        audit_log_path=str(get("audit_log_path")),
    )


def write_config_value(path: Path, key: str, value: str) -> None:
    """Rewrite one top-level ``key = "value"`` line in config.toml, leaving
    every other byte alone — the file is comment-heavy and those comments
    are load-bearing documentation, so a parse-and-redump (which would need
    a TOML writer dependency anyway) is off the table. The replaced line's
    own trailing comment is deliberately dropped: after a model swap a
    comment describing the OLD value would be a lie.

    Commented-out ``#key = ...`` alternatives never match; a key absent
    from the file is appended. Atomic (tmp + rename), so a crash mid-write
    can't truncate the live config.
    """
    text = path.read_text(encoding="utf-8")
    line = f'{key} = "{value}"'
    pattern = re.compile(rf"^[ \t]*{re.escape(key)}[ \t]*=.*$", re.MULTILINE)
    if pattern.search(text):
        text = pattern.sub(line, text, count=1)
    else:
        if text and not text.endswith("\n"):
            text += "\n"
        text += line + "\n"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def read_bundle_conf(app_root: Path) -> tuple[str, list[str]]:
    """Best-effort read of bundle.conf's TARGET_SYSTEM/MODELS — the
    manifest package.sh writes into every bundle. Not a shell parser: it
    only recognizes the simple `KEY="value"` / `KEY=value` lines package.sh
    actually emits.
    """
    bundle_conf = app_root / "bundle.conf"
    target_system, models = "online", []
    if not bundle_conf.is_file():
        return target_system, models
    text = bundle_conf.read_text()
    m = re.search(r'^TARGET_SYSTEM=["\']?([^"\'\n]+)', text, re.MULTILINE)
    if m:
        target_system = m.group(1).strip().lower()
    m = re.search(r'^MODELS=["\']?([^"\'\n]*)', text, re.MULTILINE)
    if m:
        models = [x for x in m.group(1).split() if x]
    return target_system, models

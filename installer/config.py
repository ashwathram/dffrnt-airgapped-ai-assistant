"""Reads config.toml the same way dffrnt_ctrl_panel.sh's `cfg()` shell
function does: env var wins, then the file, then a hardcoded default —
never an error for a missing key. See deploy/dffrnt_ctrl_panel.sh.
"""

from __future__ import annotations

import os
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
    """Locates the directory holding docker-compose.yml + config.toml —
    HERE in dffrnt_ctrl_panel.sh. Two layouts are expected:

      dev checkout:  repo/installer/  (this package) + repo/deploy/
      installed bundle: everything (compose file, ctrl panel, config) sits
        together in one directory, same as today's dffrnt_ctrl_panel.sh.

    DFFRNT_APP_ROOT overrides both, mirroring DFFRNT_CONFIG's role for the
    config file itself.
    """
    env_path = os.environ.get("DFFRNT_APP_ROOT")
    if env_path:
        return Path(env_path)
    here = Path(__file__).resolve().parent
    for candidate in (here.parent / "deploy", here, here.parent):
        if (candidate / "docker-compose.yml").is_file():
            return candidate
    # Nothing found — fall back to the dev-checkout layout; callers surface
    # a clear error themselves when docker-compose.yml still isn't there.
    return here.parent / "deploy"


def find_config(app_root: Path) -> Path | None:
    """Mirrors dffrnt_ctrl_panel.sh's CONFIG resolution: $DFFRNT_CONFIG, else
    <app_root>/config.toml, else <app_root>/../config.toml (bare dev
    checkout, where deploy/ sits next to the repo-root config.toml).
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

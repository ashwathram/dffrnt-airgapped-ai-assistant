"""Single source of truth for every tunable parameter.

Precedence (lowest to highest):

    1. dataclass defaults below
    2. a TOML file (``./config.toml`` or the path in ``$DFFRNT_CONFIG``)
    3. environment variables (the field name upper-cased, e.g. ``API_PORT``)

Nothing here has import-time side effects, so importing the config is cheap and
safe (including from tests).
"""

import os
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Optional

# Deployment targets that should run Ollama with GPU acceleration by default.
# The environment only affects GPU acceleration — the LLM model is always taken
# from `llm_model` (config.toml / env), never derived from the environment.
GPU_ENVIRONMENTS = {"local-cuda"}


@dataclass
class Settings:
    # -- Deployment --------------------------------------------------------
    environment: str = "aws"
    gpu: bool = False                  # enable Ollama GPU acceleration in compose

    # -- Ollama (LLM + embeddings) ----------------------------------------
    ollama_url: str = "http://localhost:11434"
    llm_model: str = "qwen3:4b"        # always from config.toml / env
    embed_model: str = "nomic-embed-text"
    vector_size: int = 768             # must match `embed_model` output dim
    llm_temperature: float = 0.1
    llm_timeout: int = 600             # seconds; generation can be slow

    # -- Qdrant vector store ----------------------------------------------
    qdrant_url: str = "http://localhost:6333"
    collection_name: str = "dffrnt_documents"
    distance: str = "cosine"           # cosine | dot | euclid
    top_k: int = 5

    # -- Chunking ----------------------------------------------------------
    chunk_strategy: str = "recursive"  # fixed | sentence | paragraph | recursive
    chunk_size: int = 512
    chunk_overlap: int = 64

    # -- Retrieval / prompting --------------------------------------------
    history_turns: int = 6
    system_prompt: str = ""            # blank -> default in rag/prompt.py

    # -- API / paths -------------------------------------------------------
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    data_dir: str = "data"             # where uploaded files are stored
    source_root: str = "database/raw"  # default folder for batch ingestion
    audit_log_path: str = "logs/audit.jsonl"

    def __post_init__(self) -> None:
        if self.environment in GPU_ENVIRONMENTS:
            self.gpu = True


def _coerce(example, value):
    """Coerce a string (from env/TOML) to the type of the dataclass default."""
    if isinstance(example, bool):
        return str(value).strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(example, int) and not isinstance(value, bool):
        return int(value)
    if isinstance(example, float):
        return float(value)
    return value


def load_settings(config_path: Optional[str] = None) -> Settings:
    """Build a :class:`Settings` from defaults, then TOML, then environment."""
    defaults = Settings()
    data: dict = {}

    path = config_path or os.getenv("DFFRNT_CONFIG") or "config.toml"
    toml_path = Path(path)
    if toml_path.exists():
        with toml_path.open("rb") as fh:
            data.update(tomllib.load(fh))

    for f in fields(Settings):
        env_value = os.getenv(f.name.upper())
        if env_value is not None:
            data[f.name] = env_value

    kwargs = {
        f.name: _coerce(getattr(defaults, f.name), data[f.name])
        for f in fields(Settings)
        if f.name in data and data[f.name] is not None
    }
    return Settings(**kwargs)

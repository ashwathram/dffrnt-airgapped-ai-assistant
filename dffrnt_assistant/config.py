"""Single source of truth for every tunable parameter.

Precedence (lowest to highest): dataclass defaults, a TOML file
(``./config.toml`` or ``$DFFRNT_CONFIG``), then environment variables (the
field name upper-cased, e.g. ``API_PORT``). No import-time side effects.
"""

import os
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Optional

# Deployment targets that run Ollama with GPU acceleration by default. The
# environment never selects the LLM model — that is always `llm_model`.
GPU_ENVIRONMENTS = {"local-cuda"}


@dataclass
class Settings:
    """All tunables: deployment, models, generation, retrieval, chunking, paths."""

    # -- Deployment --------------------------------------------------------
    environment: str = "aws"
    gpu: bool = False                  # enable Ollama GPU acceleration in compose

    # -- Ollama (LLM + embeddings) ----------------------------------------
    ollama_url: str = "http://localhost:11434"
    llm_model: str = "qwen3:4b"
    embed_model: str = "bge-m3"
    vector_size: int = 1024            # must match `embed_model` output dim
    llm_temperature: float = 0.1
    llm_timeout: int = 600             # seconds; generation can be slow
    # num_ctx matters: Ollama defaults to 4096, which silently truncates RAG
    # prompts (retrieved docs + history). The rest are qwen3's recommended
    # sampling defaults; num_predict -1 = no output cap.
    llm_num_ctx: int = 8192
    llm_top_p: float = 0.95
    llm_top_k: int = 20
    llm_repeat_penalty: float = 1.0
    llm_num_predict: int = -1
    # Embedding task prefixes ("search_query: " etc.) — bge-m3 uses none.
    # Changing the embed model or prefixes requires re-uploading documents.
    embed_query_prefix: str = ""
    embed_document_prefix: str = ""

    # -- Qdrant vector store ----------------------------------------------
    qdrant_url: str = "http://localhost:6333"
    collection_name: str = "dffrnt_documents"
    summary_collection_name: str = "dffrnt_document_summaries"
    tags_collection_name: str = "dffrnt_tags"
    conversations_collection_name: str = "dffrnt_conversations"
    distance: str = "cosine"           # cosine | dot | euclid
    top_k: int = 8                     # candidates fetched per query
    # Relative cut: drop hits scoring more than this below the best hit, so
    # weak chunks never reach the prompt. Tuned with tests/eval. 0 disables.
    score_margin: float = 0.08
    # Aggregate (multi-document) queries additionally fetch the best chunk(s)
    # per document via grouped search, merged additively into the top-k pool,
    # so roll-ups ("rates of all candidates") cover every relevant document.
    # Triggered by plural/roll-up phrasing or a tag-scoped query. 0 disables.
    aggregate_group_limit: int = 24
    aggregate_group_size: int = 1      # chunks kept per document in grouped search

    # -- Chunking ----------------------------------------------------------
    chunk_strategy: str = "recursive"  # fixed | sentence | paragraph | recursive
    chunk_size: int = 512
    chunk_overlap: int = 64
    # Merge chunks smaller than this forward, so headings / single-line
    # fragments are never stored as useless standalone chunks. 0 disables.
    chunk_floor: int = 128

    # -- Retrieval / prompting --------------------------------------------
    history_turns: int = 6
    system_prompt: str = ""            # blank -> DEFAULT_SYSTEM_PROMPT in rag.py

    # -- API / paths -------------------------------------------------------
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    data_dir: str = "data"             # where uploaded files are stored
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

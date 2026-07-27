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


@dataclass
class Settings:
    """All tunables: deployment, models, generation, retrieval, chunking, paths."""

    # -- Deployment --------------------------------------------------------
    # Enable Ollama GPU acceleration in compose (needs the NVIDIA Container
    # Toolkit on the host). A plain flag — there are no environment presets.
    gpu: bool = False

    # -- Ollama (LLM + embeddings) ----------------------------------------
    ollama_url: str = "http://localhost:11434"
    llm_model: str = "qwen3:14b"
    embed_model: str = "bge-m3"
    vector_size: int = 1024            # must match `embed_model` output dim
    llm_temperature: float = 0.1
    llm_timeout: int = 600             # seconds; generation can be slow
    # num_ctx matters: Ollama defaults to 4096, which silently truncates RAG
    # prompts (retrieved docs + history); 16384 also leaves room for
    # num_predict. The rest are qwen3's recommended sampling values for
    # thinking mode (repeat_penalty 1.1 stops reasoning loops); num_predict
    # bounds runaway generation. Tuned in config.toml — keep in sync.
    llm_num_ctx: int = 16384
    llm_top_p: float = 0.95
    llm_top_k: int = 20
    llm_repeat_penalty: float = 1.1
    llm_num_predict: int = 5000
    # Embedding task prefixes ("search_query: " etc.) — bge-m3 uses none.
    # Changing the embed model or prefixes requires re-uploading documents.
    embed_query_prefix: str = ""
    embed_document_prefix: str = ""
    # Pin embeddings to CPU (num_gpu=0). On a GPU too small to hold the LLM and
    # the embedder at once, this keeps the LLM permanently resident instead of
    # being evicted to embed and reloaded to generate (per-prompt reload thrash).
    # Ingestion embeds get slower; interactive generation stays warm.
    embed_on_cpu: bool = False

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
    score_margin: float = 0.20
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

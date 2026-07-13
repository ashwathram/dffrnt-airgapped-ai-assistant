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
    embed_model: str = "bge-m3"
    vector_size: int = 1024            # must match `embed_model` output dim
    llm_temperature: float = 0.1
    llm_timeout: int = 600             # seconds; generation can be slow
    # Generation options passed to Ollama. num_ctx is the critical one: Ollama
    # defaults to 4096, which silently truncates RAG prompts (retrieved docs +
    # history) — measured prompts run ~2k tokens, but history and pasted
    # questions push past 4096, so we set a safe, evidence-based ceiling.
    # top_p/top_k/repeat_penalty are qwen3's recommended sampling defaults;
    # num_predict -1 means no output-length cap.
    llm_num_ctx: int = 8192
    llm_top_p: float = 0.95
    llm_top_k: int = 20
    llm_repeat_penalty: float = 1.0
    llm_num_predict: int = -1
    # Optional embedding task prefixes (some models need "search_query: " /
    # "search_document: " to tighten the similarity spread). bge-m3 does NOT use
    # prefixes, so both stay blank. Changing the embed model or these prefixes
    # requires re-uploading documents (the vector dimension changes).
    embed_query_prefix: str = ""
    embed_document_prefix: str = ""

    # -- Qdrant vector store ----------------------------------------------
    qdrant_url: str = "http://localhost:6333"
    collection_name: str = "dffrnt_documents"
    summary_collection_name: str = "dffrnt_document_summaries"
    tags_collection_name: str = "dffrnt_tags"  # tag taxonomy (managed, not vectors)
    conversations_collection_name: str = "dffrnt_conversations"  # saved chats
    distance: str = "cosine"           # cosine | dot | euclid
    top_k: int = 8                     # candidates fetched per query
    # Relative cut: drop hits scoring more than this far below the best hit, so
    # weak/noisy chunks never reach the prompt. A relative margin works where a
    # fixed floor can't (cosine scores here cluster in a narrow band). 0 disables.
    # Tuned on sample queries (eval/rag_eval.py): 0.08 keeps P@1 10/11, recall
    # 11/11 while trimming clearly-weaker chunks (0.12 was inert at top_k=8).
    score_margin: float = 0.08

    # -- Chunking ----------------------------------------------------------
    chunk_strategy: str = "recursive"  # fixed | sentence | paragraph | recursive
    chunk_size: int = 512
    chunk_overlap: int = 64
    # Minimum size for recursive-packed chunks. When > 0, tiny adjacent pieces
    # are merged forward so headings / names / single-line fragments do not get
    # stored as useless standalone chunks.
    chunk_floor: int = 128

    # -- Retrieval / prompting --------------------------------------------
    history_turns: int = 6
    system_prompt: str = ""            # blank -> default in rag/prompt.py

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

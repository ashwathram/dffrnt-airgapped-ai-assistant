from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import List

from embeddings.embedder import Embedder
from ingestion.loaders import load_file
from processing.chunker import chunk_file
from vector_store.qdrant_store import QdrantStore


def file_checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ingest_corpus(
    documents: List[Path],
    embedder: Embedder,
    corpus_root: Path,
    store: QdrantStore | None = None,
    chunking_method: str = "recursive",
    chunk_size: int = 1200,
    overlap: int = 150,
    incremental: bool = False,
    state_path: Path | None = None,
    metadata_map: dict | None = None,
):
    """Reusable ingestion pipeline.

    - `store` may be provided (useful for injecting a test or custom store).
    - `metadata_map` should be a mapping returned by `load_metadata_map`.
    Returns: (store, chunk_records, total_points, collection_name, stats)
    """
    collection_name = f"ingest_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    if store is None:
        store = QdrantStore(collection_name=collection_name)

    state: dict = {}
    if incremental and state_path and state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            prev_collection = state.get("collection_name")
            if prev_collection:
                store.collection_name = prev_collection
        except Exception:
            state = {}

    if not incremental or not state.get("collection_name"):
        store.recreate_collection(vector_size=embedder.dim)
        if state_path is not None:
            state.setdefault("collection_name", store.collection_name)

    chunk_records: list[dict] = []
    total_points = 0
    failed_files: list[dict] = []
    embedding_dims: list[int] = []
    embeddings_created = 0

    file_cache: dict = state.get("files", {}) if state else {}

    for index, document_path in enumerate(documents, start=1):
        checksum = None
        try:
            checksum = file_checksum(document_path)
        except Exception:
            checksum = None

        cache_entry = file_cache.get(str(document_path)) if file_cache else None
        if incremental and cache_entry and checksum and cache_entry.get("checksum") == checksum:
            cached_chunk_count = int(cache_entry.get("chunk_count") or 0)
            total_points += cached_chunk_count
            continue

        try:
            loaded = load_file(str(document_path))
        except Exception as e:
            failed_files.append({"path": str(document_path), "error": str(e)})
            continue

        chunks = chunk_file(
            loaded, strategy=chunking_method, chunk_size=chunk_size, overlap=overlap
        )
        if not chunks:
            continue

        if incremental and cache_entry and checksum and cache_entry.get("checksum") != checksum:
            store.delete_by_source_file(str(document_path))

        vectors = embedder.embed_texts([chunk["text"] for chunk in chunks])
        for v in vectors:
            try:
                embedding_dims.append(len(v))
            except Exception:
                embedding_dims.append(None)
        embeddings_created += len(vectors)

        points = []
        for chunk, vector in zip(chunks, vectors):
            chunk_record = {
                "source_file": chunk.get("source_file") or str(document_path),
                "filename": chunk.get("filename") or document_path.name,
                "document_title": loaded.get("document_title"),
                "file_type": loaded.get("file_type"),
                "chunk_id": chunk["chunk_id"],
                "char_start": chunk.get("char_start"),
                "char_end": chunk.get("char_end"),
                "page_number": chunk.get("page_number"),
                "slide_index": chunk.get("slide_index"),
                "section_heading": chunk.get("section_heading"),
                "text": chunk["text"],
                "document_type": None,
                "department": None,
                "client_project": None,
                "tags": [],
                "tag_paths": [],
            }
            if metadata_map:
                meta = metadata_map.get(str(document_path)) or metadata_map.get(document_path.name)
                if isinstance(meta, dict):
                    for k in ["document_type", "department", "client_project", "tags", "tag_paths"]:
                        if k in meta and meta.get(k) is not None:
                            chunk_record[k] = meta.get(k)
            chunk_records.append(chunk_record)
            points.append(
                {
                    "id": str(uuid.uuid5(uuid.NAMESPACE_URL, chunk["chunk_id"])),
                    "vector": vector,
                    "payload": chunk_record,
                }
            )

        store.upsert(points)
        total_points += len(points)

        if state is not None and state_path is not None:
            file_cache_entry = {
                "checksum": checksum,
                "processed_at": datetime.now().isoformat(timespec="seconds"),
                "chunk_count": len(points),
            }
            file_cache[str(document_path)] = file_cache_entry
            state["files"] = file_cache
            try:
                state_path.parent.mkdir(parents=True, exist_ok=True)
                compact_state = {
                    "collection_name": state.get("collection_name", store.collection_name),
                    "files": {
                        path: {
                            "checksum": entry.get("checksum"),
                            "processed_at": entry.get("processed_at"),
                            "chunk_count": entry.get("chunk_count"),
                        }
                        for path, entry in file_cache.items()
                    },
                }
                state_path.write_text(json.dumps(compact_state, indent=2), encoding="utf-8")
            except Exception:
                pass

    if incremental and state_path is not None:
        try:
            state_path.parent.mkdir(parents=True, exist_ok=True)
            compact_state = {
                "collection_name": state.get("collection_name", store.collection_name),
                "files": {
                    path: {
                        "checksum": entry.get("checksum"),
                        "processed_at": entry.get("processed_at"),
                        "chunk_count": entry.get("chunk_count"),
                    }
                    for path, entry in file_cache.items()
                },
            }
            state_path.write_text(json.dumps(compact_state, indent=2), encoding="utf-8")
        except Exception:
            pass

    embedding_dimension = embedding_dims[0] if embedding_dims else None
    dimension_consistent = (
        all(d == embedding_dimension for d in embedding_dims) if embedding_dims else True
    )

    stats = {
        "failed_files": failed_files,
        "embeddings_created": embeddings_created,
        "embedding_dims": embedding_dims,
        "embedding_dimension": embedding_dimension,
        "dimension_consistent": dimension_consistent,
    }

    return store, chunk_records, total_points, store.collection_name, stats

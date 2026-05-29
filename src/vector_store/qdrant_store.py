"""Simple Qdrant client wrapper. Includes helper to produce Docker run command."""

from qdrant_client import QdrantClient
from qdrant_client.http import models as rest_models
from typing import List, Dict, Optional, Any, cast
import logging

logger = logging.getLogger(__name__)


def qdrant_docker_command(port: int = 6333) -> str:
    return (
        f"docker run -d --name qdrant -p {port}:6333 -v qdrant_data:/qdrant/storage qdrant/qdrant"
    )


class QdrantStore:
    def __init__(self, url: str = "http://localhost:6333", collection_name: str = "documents"):
        self.url = url
        # qdrant-client types vary between versions; keep as Any for typing flexibility
        self.client: Any = QdrantClient(url=url)
        self.collection_name = collection_name

    def recreate_collection(self, vector_size: int, distance: str = "COSINE"):
        dist = getattr(rest_models.Distance, distance.upper(), rest_models.Distance.COSINE)
        try:
            # recreate: delete if exists then create
            self.client.recreate_collection(
                collection_name=self.collection_name,
                vectors_config=rest_models.VectorParams(size=vector_size, distance=dist),
            )
            logger.info(
                f"Recreated collection {self.collection_name} (size={vector_size} distance={dist})"
            )
        except Exception:
            logger.exception("Failed to recreate collection")
            raise

    def upsert(self, points: List[Dict], batch_size: int = 128):
        """Upsert points with `id`, `vector`, and `payload`."""
        for i in range(0, len(points), batch_size):
            batch = points[i : i + batch_size]
            client_any = cast(Any, self.client)
            client_any.upsert(collection_name=self.collection_name, points=cast(Any, batch))

    def delete_by_source_file(self, source_file: str):
        """Delete all points whose payload source_file matches the given path."""
        points_selector = rest_models.Filter(
            must=[
                rest_models.FieldCondition(
                    key="source_file",
                    match=rest_models.MatchValue(value=source_file),
                )
            ]
        )
        client_any = cast(Any, self.client)
        client_any.delete(collection_name=self.collection_name, points_selector=points_selector)

    def search(
        self, query_vector: List[float], top: int = 5, filter: Optional[dict] = None
    ) -> List[Dict]:
        """Return a list of result dicts: {id, score, payload} for the top matches.

        Accepts an optional `filter` payload dict passed to Qdrant.
        """
        results = []
        # qdrant-client API changed across versions:
        # - older: client.search(...)
        # - newer: client.query_points(...)
        if hasattr(self.client, "search"):
            kwargs = {
                "collection_name": self.collection_name,
                "query_vector": query_vector,
                "top": top,
            }
            if filter is not None:
                kwargs["filter"] = filter
            client_any = cast(Any, self.client)
            resp = client_any.search(**cast(Any, kwargs))
            for item in resp:
                # item may have .id, .payload, .score
                pid = getattr(item, "id", None) or getattr(item, "point_id", None)
                payload = getattr(item, "payload", {}) or {}
                score = getattr(item, "score", None)
                results.append({"id": pid, "score": score, "payload": payload})
            return results

        if hasattr(self.client, "query_points"):
            kwargs = {
                "collection_name": self.collection_name,
                "query": query_vector,
                "limit": top,
            }
            if filter is not None:
                # newer qdrant-client versions use query_filter for query_points
                kwargs["query_filter"] = filter
            client_any = cast(Any, self.client)
            resp = client_any.query_points(**cast(Any, kwargs))
            points = getattr(resp, "points", None) or resp
            for item in points:
                pid = getattr(item, "id", None) or getattr(item, "point_id", None)
                payload = getattr(item, "payload", {}) or {}
                score = getattr(item, "score", None)
                results.append({"id": pid, "score": score, "payload": payload})
            return results

        raise AttributeError("QdrantClient has neither 'search' nor 'query_points' methods")

    def hybrid_search(
        self,
        query_vector: List[float],
        candidate_top_k: int = 50,
        similarity_threshold: Optional[float] = None,
        filter: Optional[dict] = None,
        dedupe: bool = True,
        reranker_func=None,
    ) -> List[Dict]:
        """Search, threshold, dedupe, and optionally rerank candidates."""
        # 1) vector candidates
        candidates = self.search(query_vector, top=candidate_top_k, filter=filter)

        # 2) apply similarity threshold if provided
        if similarity_threshold is not None:
            filtered: List[Dict] = []
            for c in candidates:
                s = c.get("score")
                if s is None:
                    continue
                try:
                    if float(s) >= float(similarity_threshold):
                        filtered.append(c)
                except (TypeError, ValueError):
                    continue
            candidates = filtered

        # 3) deduplicate exact text duplicates (keep highest score)
        if dedupe:
            seen_text: dict[str, Dict[str, Any]] = {}
            unique_candidates = []
            for c in candidates:
                text = (c.get("payload") or {}).get("text")
                if text is None:
                    unique_candidates.append(c)
                    continue
                key = text.strip()
                existing = seen_text.get(key)
                if existing is None:
                    seen_text[key] = c
                else:
                    # keep higher score
                    if (c.get("score") or 0) > (existing.get("score") or 0):
                        seen_text[key] = c
            # preserve original ordering by score
            unique_candidates = sorted(
                seen_text.values(), key=lambda x: (x.get("score") or 0), reverse=True
            )
            candidates = unique_candidates

        # 4) optional reranking
        if reranker_func is not None and callable(reranker_func):
            try:
                candidates = reranker_func(query_vector, candidates)
            except Exception:
                logger.exception("Reranker failed; returning pre-rerank candidates")

        return candidates

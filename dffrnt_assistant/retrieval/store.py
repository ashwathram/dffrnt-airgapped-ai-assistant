"""The one Qdrant wrapper. Single collection, single payload schema."""

from typing import Dict, List

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchAny,
    MatchValue,
    PointStruct,
    VectorParams,
)

_DISTANCES = {
    "cosine": Distance.COSINE,
    "dot": Distance.DOT,
    "euclid": Distance.EUCLID,
}


class VectorStore:
    """The one Qdrant wrapper for chunk vectors: collection lifecycle, upserts,
    plain/filtered/grouped similarity search, and payload lookups by filename."""

    def __init__(self, url: str, collection_name: str, vector_size: int, distance: str = "cosine"):
        self.client = QdrantClient(url=url)
        self.collection_name = collection_name
        self.vector_size = vector_size
        self.distance = _DISTANCES.get(distance.lower(), Distance.COSINE)

    def ensure_collection(self) -> None:
        """Create the collection if it does not already exist (never destructive)."""
        existing = {c.name for c in self.client.get_collections().collections}
        if self.collection_name in existing:
            return
        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(size=self.vector_size, distance=self.distance),
        )

    def recreate_collection(self) -> None:
        """Drop and recreate the collection. Destructive — needed when the
        embedding model changes output dimension."""
        self.client.delete_collection(collection_name=self.collection_name)
        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(size=self.vector_size, distance=self.distance),
        )

    def upsert(self, points: List[Dict], batch_size: int = 128) -> None:
        for start in range(0, len(points), batch_size):
            batch = [
                PointStruct(id=p["id"], vector=p["vector"], payload=p["payload"])
                for p in points[start : start + batch_size]
            ]
            self.client.upsert(collection_name=self.collection_name, points=batch)

    def search(
        self,
        query_vector: List[float],
        top_k: int,
        tag_filter: List[str] = None,
        filenames: List[str] = None,
    ) -> List[Dict]:
        """Top-k nearest chunks, optionally restricted by tags and/or filenames."""
        must = []
        if tag_filter:
            must.append(FieldCondition(key="tags", match=MatchAny(any=list(tag_filter))))
        if filenames:
            must.append(FieldCondition(key="filename", match=MatchAny(any=list(filenames))))
        query_filter = Filter(must=must) if must else None
        results = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            limit=top_k,
            with_payload=True,
            query_filter=query_filter,
        ).points
        return [{"payload": r.payload, "score": r.score} for r in results]

    def search_grouped(
        self,
        query_vector: List[float],
        limit: int,
        group_size: int = 1,
        tag_filter: List[str] = None,
    ) -> List[Dict]:
        """Best ``group_size`` chunks from each of the top ``limit`` documents
        (grouped by filename), so aggregate queries get evidence from every
        relevant document rather than whatever global top-k includes."""
        must = []
        if tag_filter:
            must.append(FieldCondition(key="tags", match=MatchAny(any=list(tag_filter))))
        result = self.client.query_points_groups(
            collection_name=self.collection_name,
            query=query_vector,
            group_by="filename",
            limit=limit,
            group_size=group_size,
            with_payload=True,
            query_filter=Filter(must=must) if must else None,
        )
        return [
            {"payload": point.payload, "score": point.score}
            for group in result.groups
            for point in group.hits
        ]

    def payloads_by_filenames(self, filenames: List[str], limit: int = 0) -> List[Dict]:
        """Payloads for the given filenames (raise ``limit`` to fetch every
        chunk of a document)."""
        if not filenames:
            return []
        points, _ = self.client.scroll(
            collection_name=self.collection_name,
            scroll_filter=Filter(
                must=[FieldCondition(key="filename", match=MatchAny(any=list(filenames)))]
            ),
            limit=limit or max(len(filenames) * 2, 16),
            with_payload=True,
        )
        return [p.payload for p in points]

    def find_by_content_hash(self, content_hash: str) -> str | None:
        """Filename of an existing document with this content hash, if any —
        detects a byte-identical file uploaded under a different name."""
        if not content_hash:
            return None
        points, _ = self.client.scroll(
            collection_name=self.collection_name,
            scroll_filter=Filter(
                must=[FieldCondition(key="content_hash", match=MatchValue(value=content_hash))]
            ),
            limit=1,
            with_payload=True,
        )
        return points[0].payload.get("filename") if points else None

    def has_document(self, filename: str) -> bool:
        """True if any chunk for this filename is already stored."""
        result = self.client.count(
            collection_name=self.collection_name,
            count_filter=Filter(
                must=[FieldCondition(key="filename", match=MatchValue(value=filename))]
            ),
            exact=True,
        )
        return result.count > 0

    def delete_by_filename(self, filename: str) -> None:
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=Filter(
                must=[FieldCondition(key="filename", match=MatchValue(value=filename))]
            ),
        )

    def set_payload_by_filename(self, filename: str, payload: Dict) -> None:
        """Merge `payload` into every chunk of a document (e.g. to update tags)."""
        self.client.set_payload(
            collection_name=self.collection_name,
            payload=payload,
            points=Filter(
                must=[FieldCondition(key="filename", match=MatchValue(value=filename))]
            ),
        )

    def all_payloads(self, batch_size: int = 1024) -> List[Dict]:
        """Return every stored payload (used to build the document library view).
        Pages through the whole collection, so the result stays complete however
        large the corpus grows (a single capped scroll silently truncates)."""
        payloads: List[Dict] = []
        offset = None
        while True:
            points, offset = self.client.scroll(
                collection_name=self.collection_name,
                limit=batch_size,
                with_payload=True,
                offset=offset,
            )
            payloads.extend(p.payload for p in points)
            if offset is None:
                return payloads

    def count(self) -> int:
        try:
            return self.client.get_collection(self.collection_name).points_count
        except Exception:
            return 0

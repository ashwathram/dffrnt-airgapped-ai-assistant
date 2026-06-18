"""Tag taxonomy storage in a dedicated Qdrant collection (layout A: single blob).

The entire taxonomy — ``{"tag_types": [...], "tags": [...]}`` — lives in ONE
point. Qdrant requires a vector per point, so we attach a throwaway 1-D vector
and never search it; we only ``retrieve`` / ``upsert`` that single point, using
Qdrant as a tiny key-value document store. This avoids standing up a second
database just to hold a few dozen tag definitions.
"""

from typing import Dict

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

_TAXONOMY_ID = 1       # the one point that holds the whole taxonomy
_DUMMY_VECTOR = [0.0]  # unused — Qdrant just requires *a* vector per point
_EMPTY: Dict = {"tag_types": [], "tags": []}


class TagStore:
    def __init__(self, url: str, collection_name: str = "dffrnt_tags"):
        self.client = QdrantClient(url=url)
        self.collection_name = collection_name

    def ensure_collection(self) -> None:
        """Create the collection if missing (never destructive)."""
        existing = {c.name for c in self.client.get_collections().collections}
        if self.collection_name not in existing:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=1, distance=Distance.COSINE),
            )

    def load(self) -> Dict:
        """Return the stored taxonomy, or an empty one if nothing is saved yet."""
        points = self.client.retrieve(
            collection_name=self.collection_name, ids=[_TAXONOMY_ID], with_payload=True
        )
        if not points:
            return {"tag_types": [], "tags": []}
        payload = points[0].payload or {}
        return {
            "tag_types": payload.get("tag_types", []),
            "tags": payload.get("tags", []),
        }

    def save(self, taxonomy: Dict) -> None:
        """Replace the whole taxonomy (single read-modify-write blob)."""
        self.client.upsert(
            collection_name=self.collection_name,
            points=[
                PointStruct(
                    id=_TAXONOMY_ID,
                    vector=_DUMMY_VECTOR,
                    payload={
                        "tag_types": taxonomy.get("tag_types", []),
                        "tags": taxonomy.get("tags", []),
                    },
                )
            ],
        )

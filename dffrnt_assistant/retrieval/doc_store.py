"""Qdrant used as a plain document store (no vector search).

Both stores here attach a throwaway 1-D vector to each point — Qdrant requires
one — and only ever retrieve/upsert by id. This keeps the tag taxonomy and the
saved conversations in the same datastore as everything else, with no extra
database.
"""

import uuid
from typing import Dict, List, Optional

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointIdsList, PointStruct, VectorParams

_DUMMY_VECTOR = [0.0]


def _ensure_collection(client: QdrantClient, name: str) -> None:
    """Create a 1-D dummy-vector collection if missing (never destructive)."""
    existing = {c.name for c in client.get_collections().collections}
    if name not in existing:
        client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=1, distance=Distance.COSINE),
        )


class TagStore:
    """Persists the tag taxonomy — ``{"tag_types": [...], "tags": [...]}`` — as
    a single blob in one fixed point, read-modify-written whole."""

    _TAXONOMY_ID = 1

    def __init__(self, url: str, collection_name: str = "dffrnt_tags"):
        self.client = QdrantClient(url=url)
        self.collection_name = collection_name

    def ensure_collection(self) -> None:
        _ensure_collection(self.client, self.collection_name)

    def load(self) -> Dict:
        points = self.client.retrieve(
            collection_name=self.collection_name, ids=[self._TAXONOMY_ID], with_payload=True
        )
        payload = (points[0].payload or {}) if points else {}
        return {
            "tag_types": payload.get("tag_types", []),
            "tags": payload.get("tags", []),
        }

    def save(self, taxonomy: Dict) -> None:
        self.client.upsert(
            collection_name=self.collection_name,
            points=[
                PointStruct(
                    id=self._TAXONOMY_ID,
                    vector=_DUMMY_VECTOR,
                    payload={
                        "tag_types": taxonomy.get("tag_types", []),
                        "tags": taxonomy.get("tags", []),
                    },
                )
            ],
        )


def _is_uuid(value) -> bool:
    """Reject malformed ids early so a bad id reads as 'not found' (404)
    instead of a Qdrant 400 / server 500."""
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, TypeError, AttributeError):
        return False


class ConversationStore:
    """Persists saved conversations, one point per conversation keyed by UUID,
    so they can be listed, updated and deleted individually."""

    def __init__(self, url: str, collection_name: str = "dffrnt_conversations"):
        self.client = QdrantClient(url=url)
        self.collection_name = collection_name

    def ensure_collection(self) -> None:
        _ensure_collection(self.client, self.collection_name)

    def list(self) -> List[Dict]:
        """Every stored conversation payload (caller sorts / strips messages)."""
        points, _ = self.client.scroll(
            collection_name=self.collection_name, limit=10000, with_payload=True
        )
        return [p.payload for p in points]

    def get(self, conversation_id: str) -> Optional[Dict]:
        if not _is_uuid(conversation_id):
            return None
        points = self.client.retrieve(
            collection_name=self.collection_name, ids=[conversation_id], with_payload=True
        )
        return points[0].payload if points else None

    def save(self, conversation: Dict) -> None:
        self.client.upsert(
            collection_name=self.collection_name,
            points=[
                PointStruct(
                    id=conversation["id"], vector=_DUMMY_VECTOR, payload=conversation
                )
            ],
        )

    def delete(self, conversation_id: str) -> None:
        if not _is_uuid(conversation_id):
            return
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=PointIdsList(points=[conversation_id]),
        )

    def clear(self) -> int:
        points, _ = self.client.scroll(
            collection_name=self.collection_name, limit=10000, with_payload=False
        )
        ids = [p.id for p in points]
        if ids:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=PointIdsList(points=ids),
            )
        return len(ids)

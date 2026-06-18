"""Saved conversations in a dedicated Qdrant collection (point-per-conversation).

Like the tag store, this uses Qdrant as a plain document store — every point
carries a throwaway 1-D vector we never search. Each conversation is its own
point (so they can be listed, updated, and deleted individually), keyed by a
UUID. This keeps chat history in the same datastore as everything else, with no
extra database.
"""

import uuid
from typing import Dict, List, Optional

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointIdsList, PointStruct, VectorParams

_DUMMY_VECTOR = [0.0]  # unused — Qdrant just requires a vector per point


def _is_uuid(value) -> bool:
    """Point ids are UUIDs; reject malformed ids early so a bad id reads as
    'not found' (404) instead of a Qdrant 400 / server 500."""
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, TypeError, AttributeError):
        return False


class ConversationStore:
    def __init__(self, url: str, collection_name: str = "dffrnt_conversations"):
        self.client = QdrantClient(url=url)
        self.collection_name = collection_name

    def ensure_collection(self) -> None:
        existing = {c.name for c in self.client.get_collections().collections}
        if self.collection_name not in existing:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=1, distance=Distance.COSINE),
            )

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

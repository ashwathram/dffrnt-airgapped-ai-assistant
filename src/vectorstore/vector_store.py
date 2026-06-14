import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import uuid
from config import QDRANT_URL, COLLECTION_NAME, VECTOR_SIZE, TOP_K_RESULTS
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

def get_client():
    """Returns connection to local Qdrant database."""
    return QdrantClient(url=QDRANT_URL)

def create_collection(client):
    """Creates the document collection. Safe to call multiple times."""
    existing = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME in existing:
        print(f"Collection already exists: {COLLECTION_NAME}")
        return
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(
            size=VECTOR_SIZE,
            distance=Distance.COSINE,
        ),
    )
    print(f"Created collection: {COLLECTION_NAME}")

def store_chunks(client, chunks, embeddings):
    """Stores document chunks and their embeddings in Qdrant."""
    points = [
        PointStruct(
            id=str(uuid.uuid4()),
            vector=embedding,
            payload={
                "text":     chunk["text"],
                "filename": chunk["metadata"].get("filename", "unknown"),
                "page":     chunk["metadata"].get("page", 0),
                "chunk_id": chunk["metadata"].get("chunk_index", 0),
            }
        )
        for chunk, embedding in zip(chunks, embeddings)
    ]
    client.upsert(collection_name=COLLECTION_NAME, points=points)
    print(f"Stored {len(points)} chunks in Qdrant")

def search(client, query_vector, top_k=TOP_K_RESULTS):
    """Finds the most similar chunks to a query vector."""
    # qdrant-client >= 1.7 replaced .search() with .query_points()
    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        limit=top_k,
        with_payload=True,
    ).points
    return [
        {
            "text":     r.payload["text"],
            "filename": r.payload["filename"],
            "page":     r.payload["page"],
            "score":    round(r.score, 4),
        }
        for r in results
    ]

if __name__ == "__main__":
    print("Testing M2 Vector Store...")

    client = get_client()
    print("Connected to Qdrant: OK")

    create_collection(client)

    test_chunks = [{
        "text": "DFFRNT is a management consulting firm specializing in AI solutions.",
        "metadata": {"filename": "test.txt", "page": 1, "chunk_index": 0}
    }]
    test_embeddings = [[0.1] * 768]
    store_chunks(client, test_chunks, test_embeddings)

    results = search(client, [0.1] * 768, top_k=1)
    assert len(results) > 0, "Search returned no results"
    print(f"Search result: {results[0]['text'][:60]}...")

    print("\nM2 test PASSED ✓")

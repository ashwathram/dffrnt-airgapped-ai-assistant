"""Embedder wrapper using sentence-transformers with a fallback stub.

Provides `Embedder` with `embed_texts(texts)` returning a list of vectors.
"""
from typing import List
import numpy as np


class Embedder:
    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        self.model_name = model_name
        self.model = None
        try:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(model_name)
            # infer vector size
            self.dim = self.model.get_sentence_embedding_dimension()
        except Exception:
            # fallback to dummy embedder
            self.model = None
            self.dim = 384

    def embed_texts(self, texts: List[str], batch_size: int = 32) -> List[List[float]]:
        if self.model is None:
            # deterministic pseudo-embeddings using hash -> numpy
            vecs = []
            for t in texts:
                h = abs(hash(t))
                rng = np.random.RandomState(h % (2 ** 32))
                vec = rng.rand(self.dim).astype(float)
                vecs.append(vec.tolist())
            return vecs

        all_vecs = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i+batch_size]
            vecs = self.model.encode(batch, show_progress_bar=False)
            all_vecs.extend(vecs.tolist())
        return all_vecs

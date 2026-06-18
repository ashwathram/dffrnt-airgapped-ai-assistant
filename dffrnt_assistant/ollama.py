"""LLM management: a direct Ollama client for embeddings and text generation.

Uses only the standard library (``urllib``), so the air-gapped bundle needs no
HTTP or ML client dependency. Replaces langchain-ollama / sentence-transformers.
"""

import json
import urllib.error
import urllib.request
from typing import List


class OllamaClient:
    def __init__(
        self,
        base_url: str,
        llm_model: str,
        embed_model: str,
        temperature: float = 0.1,
        timeout: int = 600,
    ):
        self.base_url = base_url.rstrip("/")
        self.llm_model = llm_model
        self.embed_model = embed_model
        self.temperature = temperature
        self.timeout = timeout
        # Newer Ollama exposes a batch /api/embed; fall back to /api/embeddings.
        self._use_batch_embed = True

    def _post(self, path: str, payload: dict) -> dict:
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    # -- Embeddings --------------------------------------------------------
    def embed_texts(self, texts: List[str], batch_size: int = 64) -> List[List[float]]:
        """Embed texts in bounded batches (large single requests are unreliable)."""
        if not texts:
            return []
        vectors: List[List[float]] = []
        for start in range(0, len(texts), batch_size):
            vectors.extend(self._embed(texts[start : start + batch_size]))
        return vectors

    def _embed(self, texts: List[str]) -> List[List[float]]:
        if self._use_batch_embed:
            try:
                out = self._post("/api/embed", {"model": self.embed_model, "input": texts})
                embeddings = out.get("embeddings")
                if embeddings:
                    return embeddings
            except urllib.error.HTTPError as exc:
                if exc.code != 404:
                    raise
                self._use_batch_embed = False  # older Ollama; use classic endpoint
        return [
            self._post("/api/embeddings", {"model": self.embed_model, "prompt": text})[
                "embedding"
            ]
            for text in texts
        ]

    def embed_query(self, text: str) -> List[float]:
        return self.embed_texts([text])[0]

    # -- Generation --------------------------------------------------------
    def generate(self, prompt: str) -> str:
        out = self._post(
            "/api/generate",
            {
                "model": self.llm_model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": self.temperature},
            },
        )
        return out.get("response", "")

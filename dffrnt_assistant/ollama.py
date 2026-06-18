"""LLM management: a direct Ollama client for embeddings and text generation.

Uses only the standard library (``urllib``), so the air-gapped bundle needs no
HTTP or ML client dependency. Replaces langchain-ollama / sentence-transformers.
"""

import json
import urllib.error
import urllib.request
from typing import Iterator, List, Tuple


class OllamaClient:
    def __init__(
        self,
        base_url: str,
        llm_model: str,
        embed_model: str,
        temperature: float = 0.1,
        timeout: int = 600,
        query_prefix: str = "",
        doc_prefix: str = "",
    ):
        self.base_url = base_url.rstrip("/")
        self.llm_model = llm_model
        self.embed_model = embed_model
        self.temperature = temperature
        self.timeout = timeout
        # Embedding task prefixes (e.g. nomic's "search_query: "/"search_document: ").
        # embed_texts stays raw; the query/document helpers apply them.
        self.query_prefix = query_prefix
        self.doc_prefix = doc_prefix
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

    def embed_documents(self, texts: List[str], batch_size: int = 64) -> List[List[float]]:
        """Embed documents for storage, with the document task prefix applied."""
        return self.embed_texts([self.doc_prefix + t for t in texts], batch_size)

    def embed_query(self, text: str) -> List[float]:
        """Embed a search query, with the query task prefix applied."""
        return self.embed_texts([self.query_prefix + text])[0]

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

    def generate_stream(self, prompt: str) -> Iterator[Tuple[str, str]]:
        """Yield ``(channel, text)`` pairs as Ollama produces them.

        ``channel`` is "thinking" for a reasoning model's chain-of-thought
        (Ollama exposes it in a separate ``thinking`` field) or "answer" for the
        final response text. Ollama's /api/generate with stream=True returns
        newline-delimited JSON objects; urllib reads them off the socket
        incrementally, so tokens are yielded as they are generated.
        """
        data = json.dumps(
            {
                "model": self.llm_model,
                "prompt": prompt,
                "stream": True,
                "options": {"temperature": self.temperature},
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + "/api/generate",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            for line in response:
                line = line.strip()
                if not line:
                    continue
                chunk = json.loads(line.decode("utf-8"))
                thinking = chunk.get("thinking")
                if thinking:
                    yield ("thinking", thinking)
                token = chunk.get("response", "")
                if token:
                    yield ("answer", token)
                if chunk.get("done"):
                    break

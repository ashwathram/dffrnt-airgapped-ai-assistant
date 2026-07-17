"""A direct Ollama client for embeddings and text generation, using only the
standard library (``urllib``) so the air-gapped bundle ships no ML client."""

import json
import urllib.error
import urllib.request
from typing import Iterator, List, Optional, Tuple


class OllamaClient:
    """Talks to one Ollama server for both roles: embedding texts/queries
    (``embed_*``) and generating answers (``generate`` / ``generate_stream``)."""

    def __init__(
        self,
        base_url: str,
        llm_model: str,
        embed_model: str,
        temperature: float = 0.1,
        timeout: int = 600,
        query_prefix: str = "",
        doc_prefix: str = "",
        num_ctx: int = 8192,
        top_p: float = 0.95,
        top_k: int = 20,
        repeat_penalty: float = 1.0,
        num_predict: int = -1,
        embed_on_cpu: bool = False,
    ):
        self.base_url = base_url.rstrip("/")
        self.llm_model = llm_model
        self.embed_model = embed_model
        self.temperature = temperature
        self.timeout = timeout
        self.query_prefix = query_prefix
        self.doc_prefix = doc_prefix
        # num_ctx matters: Ollama defaults it to 4096, which silently truncates
        # RAG prompts once retrieved documents + history grow (see config.py).
        self.gen_options = {
            "temperature": temperature,
            "num_ctx": num_ctx,
            "top_p": top_p,
            "top_k": top_k,
            "repeat_penalty": repeat_penalty,
            "num_predict": num_predict,
        }
        # When the GPU can't hold the LLM and the embedder at once, pin
        # embeddings to CPU (num_gpu=0) so the LLM stays resident. None means
        # "send no options" and let Ollama place the embedder itself.
        self.embed_options = {"num_gpu": 0} if embed_on_cpu else None
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
                payload = {"model": self.embed_model, "input": texts}
                if self.embed_options:
                    payload["options"] = self.embed_options
                out = self._post("/api/embed", payload)
                embeddings = out.get("embeddings")
                if embeddings:
                    return embeddings
            except urllib.error.HTTPError as exc:
                if exc.code != 404:
                    raise
                self._use_batch_embed = False  # older Ollama; use classic endpoint
        vectors: List[List[float]] = []
        for text in texts:
            payload = {"model": self.embed_model, "prompt": text}
            if self.embed_options:
                payload["options"] = self.embed_options
            vectors.append(self._post("/api/embeddings", payload)["embedding"])
        return vectors

    def embed_documents(self, texts: List[str], batch_size: int = 64) -> List[List[float]]:
        """Embed documents for storage, with the document task prefix applied."""
        return self.embed_texts([self.doc_prefix + t for t in texts], batch_size)

    def embed_query(self, text: str) -> List[float]:
        """Embed a search query, with the query task prefix applied."""
        return self.embed_texts([self.query_prefix + text])[0]

    # -- Warmup ------------------------------------------------------------
    def warmup(self) -> None:
        """Load both models into memory so the first real request skips the
        model-load stall (with OLLAMA_KEEP_ALIVE=-1 they then stay resident).
        A prompt-less generate makes Ollama load the LLM without generating
        anything; the same gen options are sent so the runner is created with
        the num_ctx later requests use (a mismatch would trigger a reload).
        The embed goes through the normal path so a CPU-pinned embedder
        (embed_on_cpu) is loaded exactly where later requests expect it."""
        self._post(
            "/api/generate",
            {
                "model": self.llm_model,
                "stream": False,
                "options": self.gen_options,
                "keep_alive": -1,
            },
        )
        self.embed_texts(["warmup"])

    # -- Generation --------------------------------------------------------
    def generate(self, prompt: str, think: Optional[bool] = None) -> str:
        """One-shot generation. ``think`` toggles a reasoning model's thinking
        pass (None sends nothing, keeping the model's default). A model
        without thinking support rejects the field with a 400, so retry
        without it rather than failing the caller."""
        payload = {
            "model": self.llm_model,
            "prompt": prompt,
            "stream": False,
            "options": self.gen_options,
        }
        if think is not None:
            payload["think"] = think
        try:
            out = self._post("/api/generate", payload)
        except urllib.error.HTTPError as exc:
            if think is None or exc.code != 400:
                raise
            retry = {k: v for k, v in payload.items() if k != "think"}
            out = self._post("/api/generate", retry)
        return out.get("response", "")

    def generate_stream(self, prompt: str) -> Iterator[Tuple[str, str]]:
        """Yield ``(channel, text)`` pairs as Ollama produces them, where
        ``channel`` is "thinking" (a reasoning model's chain-of-thought) or
        "answer". Ollama streams ndjson; urllib reads it off the socket
        incrementally, so tokens arrive as they are generated."""
        data = json.dumps(
            {
                "model": self.llm_model,
                "prompt": prompt,
                "stream": True,
                "options": self.gen_options,
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

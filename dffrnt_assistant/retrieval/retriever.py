"""Query assembly: embed a question, fetch the nearest chunks, and turn them
into the context block and source citations the RAG layer consumes."""

import time
from typing import Dict, List

from ..schema import page_label, to_source


class Retriever:
    def __init__(self, store, embedder, settings, summary_store=None, audit=None):
        self.store = store
        self.embedder = embedder
        self.settings = settings
        self.summary_store = summary_store
        self.audit = audit

    def _log_perf(self, **data) -> None:
        if self.audit is not None:
            self.audit.write("PERF", data)

    def retrieve(self, question: str, tag_filter: List[str] = None) -> List[Dict]:
        """Return up to top-k hits as ``[{"payload": ..., "score": ...}, ...]``,
        optionally scoped to documents carrying any of ``tag_filter``.

        Hits scoring more than ``score_margin`` below the best hit are dropped, so
        clearly-weaker (noisy) chunks never reach the prompt. The top hit is
        always kept; with ``score_margin`` 0 the cut is disabled."""
        t0 = time.perf_counter()
        query_vector = self.embedder.embed_query(question)
        embed_ms = (time.perf_counter() - t0) * 1000
        hits = []
        summary_hits: List[Dict] = []
        summary_ms = 0.0
        chunk_ms = 0.0
        candidate_files: List[str] = []
        if self.summary_store is not None:
            t1 = time.perf_counter()
            summary_hits = self.summary_store.search(query_vector, self.settings.top_k, tag_filter)
            summary_ms = (time.perf_counter() - t1) * 1000
            for hit in summary_hits:
                filename = hit["payload"].get("filename")
                if filename and filename not in candidate_files:
                    candidate_files.append(filename)
            if candidate_files:
                t2 = time.perf_counter()
                hits = self.store.search(query_vector, self.settings.top_k, tag_filter, candidate_files)
                chunk_ms = (time.perf_counter() - t2) * 1000
        if not hits:
            t2 = time.perf_counter()
            hits = self.store.search(query_vector, self.settings.top_k, tag_filter)
            chunk_ms = (time.perf_counter() - t2) * 1000
        margin = getattr(self.settings, "score_margin", 0) or 0
        if hits and margin > 0:
            cutoff = hits[0]["score"] - margin
            hits = [h for h in hits if h["score"] >= cutoff]
        self._log_perf(
            stage="retrieve",
            embed_ms=round(embed_ms, 2),
            summary_ms=round(summary_ms, 2),
            chunk_ms=round(chunk_ms, 2),
            total_ms=round((time.perf_counter() - t0) * 1000, 2),
            summary_hits=len(summary_hits),
            candidate_files=len(candidate_files),
            hits=len(hits),
            tag_filter=tag_filter or [],
        )
        return hits

    @staticmethod
    def build_context(hits: List[Dict]) -> str:
        """Render hits as <document> tags for the prompt."""
        blocks = []
        for index, hit in enumerate(hits, start=1):
            payload = hit["payload"]
            blocks.append(
                f'<document index="{index}" '
                f'source="{payload.get("filename")}" '
                f'page="{page_label(payload)}">\n'
                f'{payload.get("text", "")}\n</document>'
            )
        return "\n\n".join(blocks)

    @staticmethod
    def sources(hits: List[Dict]) -> List[Dict]:
        return [to_source(hit["payload"], hit["score"]) for hit in hits]

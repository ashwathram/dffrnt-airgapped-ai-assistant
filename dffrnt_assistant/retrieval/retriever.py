"""Query assembly: embed a question, fetch the nearest chunks, and turn them
into the context block and source citations the RAG layer consumes."""

from typing import Dict, List, Optional

from ..schema import page_label, to_source


class Retriever:
    def __init__(self, store, embedder, settings):
        self.store = store
        self.embedder = embedder
        self.settings = settings

    def retrieve(
        self,
        question: str,
        tag_filter: List[str] = None,
        filename_filter: Optional[List[str]] = None,
        top_k: Optional[int] = None,
    ) -> List[Dict]:
        """Return up to top-k hits as ``[{"payload": ..., "score": ...}, ...]``,
        optionally scoped to documents carrying any of ``tag_filter`` and/or
        whose filenames match one of ``filename_filter``.

        Hits scoring more than ``score_margin`` below the best hit are dropped, so
        clearly-weaker (noisy) chunks never reach the prompt. The top hit is
        always kept; with ``score_margin`` 0 the cut is disabled."""
        query_vector = self.embedder.embed_query(question)
        hits = self.store.search(
            query_vector,
            top_k or self.settings.top_k,
            tag_filter,
            filename_filter,
        )
        margin = getattr(self.settings, "score_margin", 0) or 0
        if hits and margin > 0:
            cutoff = hits[0]["score"] - margin
            hits = [h for h in hits if h["score"] >= cutoff]
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

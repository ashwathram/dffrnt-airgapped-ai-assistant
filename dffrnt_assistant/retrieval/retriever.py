"""Query assembly: embed a question, fetch the nearest chunks, and turn them
into the context block and source citations the RAG layer consumes."""

from typing import Dict, List

from ..schema import page_label, to_source


class Retriever:
    def __init__(self, store, embedder, settings):
        self.store = store
        self.embedder = embedder
        self.settings = settings

    def retrieve(self, question: str) -> List[Dict]:
        """Return the top-k hits as ``[{"payload": ..., "score": ...}, ...]``."""
        query_vector = self.embedder.embed_query(question)
        return self.store.search(query_vector, self.settings.top_k)

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

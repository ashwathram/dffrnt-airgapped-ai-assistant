"""The RAG pipeline: retrieve -> assemble prompt -> generate."""

from typing import Iterator, List, Optional, Tuple

from .prompt import DEFAULT_SYSTEM_PROMPT, build_history, build_prompt

_NO_DOCUMENTS = (
    "No documents have been ingested yet. Please ask an admin to upload documents."
)
_NO_MATCHING_TAGS = (
    "No documents match the selected tag filter. Clear the filter or choose "
    "different tags, then try again."
)


def _no_hits_message(tag_filter) -> str:
    return _NO_MATCHING_TAGS if tag_filter else _NO_DOCUMENTS


class RagPipeline:
    def __init__(self, retriever, llm, settings):
        self.retriever = retriever
        self.llm = llm
        self.settings = settings
        self.system_prompt = settings.system_prompt or DEFAULT_SYSTEM_PROMPT

    def answer(
        self, question: str, history: Optional[List[dict]] = None, tag_filter=None
    ) -> dict:
        hits = self.retriever.retrieve(question, tag_filter)
        if not hits:
            return {"answer": _no_hits_message(tag_filter), "sources": [], "question": question}

        context = self.retriever.build_context(hits)
        history_text = build_history(history or [], self.settings.history_turns)
        prompt = build_prompt(self.system_prompt, context, history_text, question)

        return {
            "answer": self.llm.generate(prompt),
            "sources": self.retriever.sources(hits),
            "question": question,
        }

    def answer_stream(
        self, question: str, history: Optional[List[dict]] = None, tag_filter=None
    ) -> Iterator[Tuple[str, object]]:
        """Stream an answer as ``(kind, payload)`` events.

        Yields exactly one ``("sources", list)`` first (retrieval happens before
        generation, so sources are known up front), then ``("token", str)`` for
        each generated token. The caller assembles the final answer text.
        """
        hits = self.retriever.retrieve(question, tag_filter)
        if not hits:
            yield ("sources", [])
            yield ("token", _no_hits_message(tag_filter))
            return

        context = self.retriever.build_context(hits)
        history_text = build_history(history or [], self.settings.history_turns)
        prompt = build_prompt(self.system_prompt, context, history_text, question)

        yield ("sources", self.retriever.sources(hits))
        for channel, text in self.llm.generate_stream(prompt):
            yield ("thinking", text) if channel == "thinking" else ("token", text)

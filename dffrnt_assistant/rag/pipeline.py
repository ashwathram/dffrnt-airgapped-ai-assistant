"""The RAG pipeline: retrieve -> assemble prompt -> generate."""

import time
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
    def __init__(self, retriever, llm, settings, audit=None):
        self.retriever = retriever
        self.llm = llm
        self.settings = settings
        self.audit = audit
        self.system_prompt = settings.system_prompt or DEFAULT_SYSTEM_PROMPT

    def _log_perf(self, **data) -> None:
        if self.audit is not None:
            self.audit.write("PERF", data)

    def answer(
        self, question: str, history: Optional[List[dict]] = None, tag_filter=None
    ) -> dict:
        t0 = time.perf_counter()
        hits = self.retriever.retrieve(question, tag_filter)
        if not hits:
            self._log_perf(
                stage="answer",
                retrieval_ms=round((time.perf_counter() - t0) * 1000, 2),
                prompt_ms=0.0,
                generation_ms=0.0,
                total_ms=round((time.perf_counter() - t0) * 1000, 2),
                sources=0,
            )
            return {"answer": _no_hits_message(tag_filter), "sources": [], "question": question}

        t1 = time.perf_counter()
        context = self.retriever.build_context(hits)
        history_text = build_history(history or [], self.settings.history_turns)
        prompt = build_prompt(self.system_prompt, context, history_text, question)
        prompt_ms = (time.perf_counter() - t1) * 1000
        t2 = time.perf_counter()
        answer = self.llm.generate(prompt)
        generation_ms = (time.perf_counter() - t2) * 1000
        total_ms = (time.perf_counter() - t0) * 1000
        self._log_perf(
            stage="answer",
            retrieval_ms=round((t1 - t0) * 1000, 2),
            prompt_ms=round(prompt_ms, 2),
            generation_ms=round(generation_ms, 2),
            total_ms=round(total_ms, 2),
            sources=len(hits),
        )

        return {
            "answer": answer,
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
        t0 = time.perf_counter()
        hits = self.retriever.retrieve(question, tag_filter)
        if not hits:
            self._log_perf(
                stage="stream",
                retrieval_ms=round((time.perf_counter() - t0) * 1000, 2),
                prompt_ms=0.0,
                generation_ms=0.0,
                total_ms=round((time.perf_counter() - t0) * 1000, 2),
                sources=0,
            )
            yield ("sources", [])
            yield ("token", _no_hits_message(tag_filter))
            return

        t1 = time.perf_counter()
        context = self.retriever.build_context(hits)
        history_text = build_history(history or [], self.settings.history_turns)
        prompt = build_prompt(self.system_prompt, context, history_text, question)
        prompt_ms = (time.perf_counter() - t1) * 1000

        yield ("sources", self.retriever.sources(hits))
        t2 = time.perf_counter()
        try:
            for channel, text in self.llm.generate_stream(prompt):
                yield ("thinking", text) if channel == "thinking" else ("token", text)
        finally:
            self._log_perf(
                stage="stream",
                retrieval_ms=round((t1 - t0) * 1000, 2),
                prompt_ms=round(prompt_ms, 2),
                generation_ms=round((time.perf_counter() - t2) * 1000, 2),
                total_ms=round((time.perf_counter() - t0) * 1000, 2),
                sources=len(hits),
            )

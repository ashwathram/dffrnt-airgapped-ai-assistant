"""The RAG pipeline: retrieve -> assemble prompt -> generate."""

from typing import List, Optional

from .prompt import DEFAULT_SYSTEM_PROMPT, build_history, build_prompt

_NO_DOCUMENTS = (
    "No documents have been ingested yet. Please ask an admin to upload documents."
)


class RagPipeline:
    def __init__(self, retriever, llm, settings):
        self.retriever = retriever
        self.llm = llm
        self.settings = settings
        self.system_prompt = settings.system_prompt or DEFAULT_SYSTEM_PROMPT

    def answer(self, question: str, history: Optional[List[dict]] = None) -> dict:
        hits = self.retriever.retrieve(question)
        if not hits:
            return {"answer": _NO_DOCUMENTS, "sources": [], "question": question}

        context = self.retriever.build_context(hits)
        history_text = build_history(history or [], self.settings.history_turns)
        prompt = build_prompt(self.system_prompt, context, history_text, question)

        return {
            "answer": self.llm.generate(prompt),
            "sources": self.retriever.sources(hits),
            "question": question,
        }

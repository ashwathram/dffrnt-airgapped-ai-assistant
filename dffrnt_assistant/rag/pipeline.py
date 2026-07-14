"""The RAG pipeline: retrieve -> assemble prompt -> generate."""

import logging
import time
from typing import Dict, Iterator, List, Optional, Tuple

from .prompt import (
    build_history,
    build_prompt,
    build_rfp_compare_prompt,
    build_rfp_requirements_prompt,
    build_resume_capabilities_prompt,
    build_system_prompt,
)

_NO_DOCUMENTS = (
    "No documents have been ingested yet. Please ask an admin to upload documents."
)
_NO_MATCHING_TAGS = (
    "No documents match the selected tag filter. Clear the filter or choose "
    "different tags, then try again."
)


def _no_hits_message(tag_filter) -> str:
    return _NO_MATCHING_TAGS if tag_filter else _NO_DOCUMENTS


logger = logging.getLogger(__name__)


class RagPipeline:
    def __init__(self, retriever, llm, settings, audit=None):
        self.retriever = retriever
        self.llm = llm
        self.settings = settings
        self.audit = audit
        self.system_prompt = settings.system_prompt
        self.rfp_system_prompt = getattr(settings, "rfp_system_prompt", "")

    @staticmethod
    def _looks_like_rfp_tag(name: str) -> bool:
        lower = (name or "").strip().lower()
        return "rfp" in lower or "request for proposal" in lower

    def _is_rfp_payload(self, payload: Dict, selected_tags: Optional[List[str]] = None) -> bool:
        document_type = str(payload.get("document_type") or "").strip().lower()
        if document_type in {"rfp", "request_for_proposal", "request for proposal"}:
            return True
        payload_tags = [str(tag or "") for tag in (payload.get("tags") or [])]
        selected_tags = [str(tag or "") for tag in (selected_tags or [])]
        if any(self._looks_like_rfp_tag(tag) for tag in payload_tags):
            return True
        if any(self._looks_like_rfp_tag(tag) for tag in selected_tags if tag in payload_tags):
            return True
        filename = str(payload.get("filename") or "")
        lower = filename.lower()
        return "rfp" in lower or "request for proposal" in lower

    @staticmethod
    def _group_hits(hits: List[Dict]) -> List[Dict]:
        grouped: List[Dict] = []
        by_file: Dict[str, Dict] = {}
        for index, hit in enumerate(hits, start=1):
            payload = hit["payload"]
            filename = payload.get("filename") or "unknown"
            text = (payload.get("text") or "").strip()
            if not text:
                continue
            group = by_file.get(filename)
            if group is None:
                group = {"filename": filename, "blocks": []}
                by_file[filename] = group
                grouped.append(group)
            group["blocks"].append(
                {
                    "index": index,
                    "text": text,
                    "summary_kind": payload.get("summary_kind") or "",
                }
            )
        return grouped

    @staticmethod
    def _group_context(groups: List[Dict]) -> str:
        blocks = []
        for group in groups:
            blocks.append(f'<<file name="{group["filename"]}">>')
            for block in group["blocks"]:
                label = "summary" if block["summary_kind"] == "document_summary" else "evidence"
                blocks.append(f'[{block["index"]}] ({label}) {block["text"]}')
            blocks.append("<</file>>")
        return "\n".join(blocks)

    @staticmethod
    def _compact_groups(
        groups: List[Dict],
        summary_blocks: int = 1,
        evidence_blocks: int = 3,
    ) -> List[Dict]:
        compacted: List[Dict] = []
        for group in groups:
            summaries = [b for b in group["blocks"] if b["summary_kind"] == "document_summary"]
            evidence = [b for b in group["blocks"] if b["summary_kind"] != "document_summary"]
            blocks = summaries[:summary_blocks] + evidence[:evidence_blocks]
            if not blocks:
                blocks = group["blocks"][: max(summary_blocks + evidence_blocks, 1)]
            compacted.append({"filename": group["filename"], "blocks": blocks})
        return compacted

    def _rfp_answer(self, question: str, hits: List[Dict], selected_tags: Optional[List[str]] = None) -> str:
        logger.warning(
            "RFP_DEBUG _rfp_answer start question=%r hits=%d hit_filenames=%s",
            question,
            len(hits),
            [str((hit.get("payload") or {}).get("filename") or "") for hit in hits],
        )
        grouped = self._group_hits(hits)
        group_lookup = {
            group["filename"]: next(
                (hit.get("payload") or {} for hit in hits if str((hit.get("payload") or {}).get("filename") or "") == group["filename"]),
                {},
            )
            for group in grouped
        }
        rfp_groups = [
            group for group in grouped
            if self._is_rfp_payload(group_lookup.get(group["filename"], {}))
        ]
        resume_groups = [
            group for group in grouped
            if not self._is_rfp_payload(group_lookup.get(group["filename"], {}))
        ]
        if selected_tags:
            rfp_groups = [
                group for group in grouped
                if self._is_rfp_payload(group_lookup.get(group["filename"], {}), selected_tags)
            ]
            resume_groups = [
                group for group in grouped
                if not self._is_rfp_payload(group_lookup.get(group["filename"], {}), selected_tags)
            ]
        logger.warning(
            "RFP_DEBUG _rfp_answer grouped rfp_files=%s resume_files=%s",
            [g["filename"] for g in rfp_groups],
            [g["filename"] for g in resume_groups],
        )
        if not rfp_groups or not resume_groups:
            return "The available documents do not contain enough information to answer this."

        rfp_context = self._group_context(self._compact_groups(rfp_groups))
        resume_context = self._group_context(self._compact_groups(resume_groups))
        logger.warning(
            "RFP_DEBUG _rfp_answer contexts rfp_chars=%d resume_chars=%d rfp_context=%r resume_context=%r resume_context_files=%s",
            len(rfp_context),
            len(resume_context),
            rfp_context[:2000],
            resume_context[:2000],
            [g["filename"] for g in resume_groups],
        )
        requirements_prompt = build_rfp_requirements_prompt(rfp_context, question)
        logger.warning(
            "RFP_DEBUG _rfp_answer executing requirements_prompt prompt_preview=%r",
            requirements_prompt[:2000],
        )
        requirements = self.llm.generate(requirements_prompt).strip()
        logger.warning(
            "RFP_DEBUG _rfp_answer extracted_requirements=%r",
            requirements[:3000],
        )
        if not requirements:
            return "The available documents do not contain enough information to answer this."

        capabilities_prompt = build_resume_capabilities_prompt(resume_context, question)
        logger.warning(
            "RFP_DEBUG _rfp_answer executing capabilities_prompt prompt_preview=%r",
            capabilities_prompt[:2000],
        )
        capabilities = self.llm.generate(capabilities_prompt).strip()
        logger.warning(
            "RFP_DEBUG _rfp_answer extracted_resume_capabilities=%r",
            capabilities[:3000],
        )
        if not capabilities:
            return "The available documents do not contain enough information to answer this."

        compare_prompt = build_rfp_compare_prompt(requirements, capabilities, question)
        logger.warning(
            "RFP_DEBUG _rfp_answer executing compare_prompt prompt_preview=%r",
            compare_prompt[:3000],
        )
        answer = self.llm.generate(compare_prompt).strip() or (
            "The available documents do not contain enough information to answer this."
        )
        logger.warning("RFP_DEBUG _rfp_answer final_answer=%r", answer[:3000])
        return answer

    def _rfp_answer_stream(
        self,
        question: str,
        hits: List[Dict],
        selected_tags: Optional[List[str]] = None,
    ) -> Iterator[Tuple[str, str]]:
        logger.warning(
            "RFP_DEBUG _rfp_answer_stream start question=%r hits=%d hit_filenames=%s",
            question,
            len(hits),
            [str((hit.get("payload") or {}).get("filename") or "") for hit in hits],
        )
        grouped = self._group_hits(hits)
        group_lookup = {
            group["filename"]: next(
                (hit.get("payload") or {} for hit in hits if str((hit.get("payload") or {}).get("filename") or "") == group["filename"]),
                {},
            )
            for group in grouped
        }
        rfp_groups = [
            group for group in grouped
            if self._is_rfp_payload(group_lookup.get(group["filename"], {}))
        ]
        resume_groups = [
            group for group in grouped
            if not self._is_rfp_payload(group_lookup.get(group["filename"], {}))
        ]
        if selected_tags:
            rfp_groups = [
                group for group in grouped
                if self._is_rfp_payload(group_lookup.get(group["filename"], {}), selected_tags)
            ]
            resume_groups = [
                group for group in grouped
                if not self._is_rfp_payload(group_lookup.get(group["filename"], {}), selected_tags)
            ]
        logger.warning(
            "RFP_DEBUG _rfp_answer_stream grouped rfp_files=%s resume_files=%s",
            [g["filename"] for g in rfp_groups],
            [g["filename"] for g in resume_groups],
        )
        if not rfp_groups or not resume_groups:
            yield ("token", "The available documents do not contain enough information to answer this.")
            return

        rfp_context = self._group_context(self._compact_groups(rfp_groups))
        resume_context = self._group_context(self._compact_groups(resume_groups))
        logger.warning(
            "RFP_DEBUG _rfp_answer_stream contexts rfp_chars=%d resume_chars=%d rfp_context=%r resume_context=%r resume_context_files=%s",
            len(rfp_context),
            len(resume_context),
            rfp_context[:2000],
            resume_context[:2000],
            [g["filename"] for g in resume_groups],
        )

        yield ("thinking", "Extracting RFP requirements...\n")
        requirements_prompt = build_rfp_requirements_prompt(rfp_context, question)
        logger.warning(
            "RFP_DEBUG _rfp_answer_stream executing requirements_prompt prompt_preview=%r",
            requirements_prompt[:2000],
        )
        requirements = self.llm.generate(requirements_prompt).strip()
        logger.warning(
            "RFP_DEBUG _rfp_answer_stream extracted_requirements=%r",
            requirements[:3000],
        )
        if not requirements:
            yield ("token", "The available documents do not contain enough information to answer this.")
            return

        yield ("thinking", "Extracting resume capabilities...\n")
        capabilities_prompt = build_resume_capabilities_prompt(resume_context, question)
        logger.warning(
            "RFP_DEBUG _rfp_answer_stream executing capabilities_prompt prompt_preview=%r",
            capabilities_prompt[:2000],
        )
        capabilities = self.llm.generate(capabilities_prompt).strip()
        logger.warning(
            "RFP_DEBUG _rfp_answer_stream extracted_resume_capabilities=%r",
            capabilities[:3000],
        )
        if not capabilities:
            yield ("token", "The available documents do not contain enough information to answer this.")
            return

        yield ("thinking", "Comparing fit...\n")
        compare_prompt = build_rfp_compare_prompt(requirements, capabilities, question)
        logger.warning(
            "RFP_DEBUG _rfp_answer_stream executing compare_prompt prompt_preview=%r",
            compare_prompt[:3000],
        )
        answer = self.llm.generate(compare_prompt).strip() or (
            "The available documents do not contain enough information to answer this."
        )
        logger.warning("RFP_DEBUG _rfp_answer_stream final_answer=%r", answer[:3000])
        yield ("token", answer)

    def _log_perf(self, **data) -> None:
        if self.audit is not None:
            self.audit.write("PERF", data)

    def _prompt(self, mode: str, context: str, history_text: str, question: str) -> str:
        system_prompt = build_system_prompt(mode, self.system_prompt, self.rfp_system_prompt)
        return build_prompt(system_prompt, context, history_text, question)

    def answer(
        self, question: str, history: Optional[List[dict]] = None, tag_filter=None, mode: str = "chat"
    ) -> dict:
        mode = (mode or "chat").strip().lower()
        logger.warning("RFP_DEBUG answer entry mode=%r question=%r tags=%s", mode, question, tag_filter or [])
        t0 = time.perf_counter()
        hits = self.retriever.retrieve(question, tag_filter, mode=mode)
        logger.warning(
            "RFP_DEBUG answer retrieved mode=%r filenames=%s",
            mode,
            [str((hit.get("payload") or {}).get("filename") or "") for hit in hits],
        )
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
        if mode == "rfp":
            prompt_ms = (time.perf_counter() - t1) * 1000
            t2 = time.perf_counter()
            answer = self._rfp_answer(question, hits, tag_filter)
        else:
            context = self.retriever.build_context(hits)
            history_text = build_history(history or [], self.settings.history_turns)
            prompt = self._prompt(mode, context, history_text, question)
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
        self, question: str, history: Optional[List[dict]] = None, tag_filter=None, mode: str = "chat"
    ) -> Iterator[Tuple[str, object]]:
        """Stream an answer as ``(kind, payload)`` events.

        Yields exactly one ``("sources", list)`` first (retrieval happens before
        generation, so sources are known up front), then ``("token", str)`` for
        each generated token. The caller assembles the final answer text.
        """
        mode = (mode or "chat").strip().lower()
        logger.warning("RFP_DEBUG answer_stream entry mode=%r question=%r tags=%s", mode, question, tag_filter or [])
        t0 = time.perf_counter()
        hits = self.retriever.retrieve(question, tag_filter, mode=mode)
        logger.warning(
            "RFP_DEBUG answer_stream retrieved mode=%r filenames=%s",
            mode,
            [str((hit.get("payload") or {}).get("filename") or "") for hit in hits],
        )
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
        if mode == "rfp":
            prompt_ms = (time.perf_counter() - t1) * 1000
            prompt = ""
        else:
            context = self.retriever.build_context(hits)
            history_text = build_history(history or [], self.settings.history_turns)
            prompt = self._prompt(mode, context, history_text, question)
            prompt_ms = (time.perf_counter() - t1) * 1000

        yield ("sources", self.retriever.sources(hits))
        t2 = time.perf_counter()
        try:
            if mode == "rfp":
                for kind, payload in self._rfp_answer_stream(question, hits, tag_filter):
                    yield (kind, payload)
            else:
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

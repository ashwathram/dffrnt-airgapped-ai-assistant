"""Query assembly: embed a question, fetch the nearest chunks, and turn them
into the context block and source citations the RAG layer consumes."""

import logging
import time
from typing import Dict, List

from ..schema import page_label, to_source

logger = logging.getLogger(__name__)


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

    def _selected_files(self, tag_filter: List[str] = None) -> List[str]:
        selected_files: List[str] = []
        seen = set()
        for payload in self.store.all_payloads():
            payload = payload or {}
            filename = payload.get("filename")
            if not filename or filename in seen:
                continue
            payload_tags = payload.get("tags") or []
            if tag_filter and not any(tag in payload_tags for tag in tag_filter):
                continue
            seen.add(filename)
            selected_files.append(filename)
        return selected_files

    def retrieve(self, question: str, tag_filter: List[str] = None, mode: str = "chat") -> List[Dict]:
        """Return up to top-k hits as ``[{"payload": ..., "score": ...}, ...]``,
        optionally scoped to documents carrying any of ``tag_filter``.

        Hits scoring more than ``score_margin`` below the best hit are dropped, so
        clearly-weaker (noisy) chunks never reach the prompt. The top hit is
        always kept; with ``score_margin`` 0 the cut is disabled."""
        t0 = time.perf_counter()
        mode = (mode or "chat").strip().lower()
        logger.warning(
            "RFP_DEBUG retrieve entry mode=%r question=%r tag_filter=%s",
            mode,
            question,
            tag_filter or [],
        )
        query_vector = self.embedder.embed_query(question)
        embed_ms = (time.perf_counter() - t0) * 1000
        hits = []
        summary_hits: List[Dict] = []
        summary_ms = 0.0
        chunk_ms = 0.0
        candidate_files: List[str] = []
        if mode == "rfp":
            t1 = time.perf_counter()
            candidate_files = self._selected_files(tag_filter)
            if candidate_files:
                summary_limit = max(self.settings.top_k, len(candidate_files))
                summary_hits = self.summary_store.search(query_vector, summary_limit, tag_filter)
                summary_by_file: Dict[str, Dict] = {}
                ordered_files: List[str] = []
                seen_summary = set()
                for hit in summary_hits:
                    filename = hit["payload"].get("filename")
                    if filename and filename not in seen_summary:
                        seen_summary.add(filename)
                        ordered_files.append(filename)
                        summary_by_file[filename] = hit
                for filename in candidate_files:
                    if filename not in seen_summary:
                        ordered_files.append(filename)

                file_rank = {filename: idx for idx, filename in enumerate(ordered_files)}
                # Summary-first: include one summary per selected file, then a
                # small set of supporting chunks from those same files.
                hits = [summary_by_file[f] for f in ordered_files if f in summary_by_file]
                chunk_limit = max(self.settings.top_k, len(candidate_files) * 2)
                supporting_hits = self.store.search(
                    query_vector,
                    chunk_limit,
                    tag_filter,
                    candidate_files,
                )
                # Keep up to two strongest supporting chunks per file so the
                # compare step stays grounded without flooding the prompt.
                per_file: Dict[str, int] = {}
                filtered_support = []
                for hit in supporting_hits:
                    filename = str((hit.get("payload") or {}).get("filename") or "")
                    if not filename:
                        continue
                    count = per_file.get(filename, 0)
                    if count >= 2:
                        continue
                    per_file[filename] = count + 1
                    filtered_support.append(hit)
                hits.extend(filtered_support)
                hits.sort(
                    key=lambda h: (
                        file_rank.get(str(h["payload"].get("filename") or ""), len(file_rank)),
                        0 if str(h["payload"].get("summary_kind") or "") == "document_summary" else 1,
                        -float(h.get("score") or 0),
                        int(h["payload"].get("page_number") or 0),
                        int(h["payload"].get("slide_index") or 0),
                        int(h["payload"].get("char_start") or 0),
                        str(h["payload"].get("chunk_id") or ""),
                    )
                )
                chunk_ms = (time.perf_counter() - t1) * 1000
        elif mode == "resume":
            t1 = time.perf_counter()
            all_payloads = self.store.all_payloads()
            candidate_files = self._selected_files(tag_filter)
            if candidate_files:
                summary_limit = max(self.settings.top_k, len(candidate_files))
                summary_hits = self.summary_store.search(query_vector, summary_limit, tag_filter)
                ordered_files: List[str] = []
                seen_summary = set()
                for hit in summary_hits:
                    filename = hit["payload"].get("filename")
                    if filename and filename not in seen_summary:
                        seen_summary.add(filename)
                        ordered_files.append(filename)
                for filename in candidate_files:
                    if filename not in seen_summary:
                        ordered_files.append(filename)

                file_rank = {filename: idx for idx, filename in enumerate(ordered_files)}
                allowed = set(candidate_files)
                hits = [
                    {"payload": payload, "score": 1.0}
                    for payload in all_payloads
                    if (payload or {}).get("filename") in allowed
                    and (
                        not tag_filter
                        or any(tag in ((payload or {}).get("tags") or []) for tag in tag_filter)
                    )
                ]
                hits.sort(
                    key=lambda h: (
                        file_rank.get(str(h["payload"].get("filename") or ""), len(file_rank)),
                        int(h["payload"].get("page_number") or 0),
                        int(h["payload"].get("slide_index") or 0),
                        int(h["payload"].get("char_start") or 0),
                        str(h["payload"].get("chunk_id") or ""),
                    )
                )
                chunk_ms = (time.perf_counter() - t1) * 1000
        elif self.summary_store is not None:
            t1 = time.perf_counter()
            embed_ms = (time.perf_counter() - t0) * 1000
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
        if mode not in {"rfp", "resume"} and hits and margin > 0:
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
            mode=mode,
            tag_filter=tag_filter or [],
        )
        logger.warning(
            "RFP_DEBUG retrieve exit mode=%r candidate_files=%s summary_files=%s hit_filenames=%s",
            mode,
            candidate_files,
            [
                str((hit.get("payload") or {}).get("filename") or "")
                for hit in summary_hits
            ],
            [str((hit.get("payload") or {}).get("filename") or "") for hit in hits],
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
    def sources(hits: List[Dict], mode: str = "chat") -> List[Dict]:
        return [to_source(hit["payload"], hit["score"]) for hit in hits]

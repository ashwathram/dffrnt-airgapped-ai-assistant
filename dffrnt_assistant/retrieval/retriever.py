"""Query assembly: embed a question, fetch the nearest chunks, and turn them
into the context block and source citations the RAG layer consumes."""

import re
import time
from typing import Dict, List

from ..schema import page_label, to_source

# Aggregate-intent cues ("rates of all candidates", "compare the proposals").
# Deliberately loose — a false positive only adds per-document evidence that
# the margin cut then trims; it never removes anything.
_AGGREGATE_CUES = re.compile(
    r"\b(all|every|each|who|which|whose|list|compare|comparison|tabulate|table|"
    r"candidates|employees|contractors|resumes|team)\b",
    re.IGNORECASE,
)


class Retriever:
    """Embeds a question, gathers the best chunks, and renders them as the
    prompt context block + source citations the RAG layer consumes."""

    def __init__(self, store, embedder, settings, summary_store=None, audit=None):
        self.store = store
        self.embedder = embedder
        self.settings = settings
        self.summary_store = summary_store
        self.audit = audit

    def _log_perf(self, **data) -> None:
        if self.audit is not None:
            self.audit.write("PERF", data)

    def _merge(self, hits: List[Dict], extras: List[Dict]) -> tuple:
        """Add `extras` chunks not already in `hits`, keeping score order.
        Returns (merged, added_count)."""
        seen = {h["payload"].get("chunk_id") for h in hits}
        new = [h for h in extras if h["payload"].get("chunk_id") not in seen]
        if not new:
            return hits, 0
        return sorted(hits + new, key=lambda h: h["score"], reverse=True), len(new)

    def _attach_summaries(self, hits: List[Dict], summary_hits: List[Dict]) -> None:
        """Stamp each hit's payload with its document's summary, so
        build_context can brief the model on each source document once."""
        summaries: Dict[str, str] = {}
        for hit in summary_hits:
            payload = hit["payload"]
            filename = payload.get("filename")
            text = (payload.get("document_summary") or payload.get("text") or "").strip()
            if filename and text:
                summaries.setdefault(filename, text)
        hit_files = {h["payload"].get("filename") for h in hits}
        missing = [f for f in hit_files if f and f not in summaries]
        if missing:
            for payload in self.summary_store.payloads_by_filenames(missing):
                filename = payload.get("filename")
                text = (payload.get("document_summary") or payload.get("text") or "").strip()
                if filename and text:
                    summaries.setdefault(filename, text)
        for hit in hits:
            summary = summaries.get(hit["payload"].get("filename"))
            if summary:
                hit["payload"]["document_summary"] = summary

    def retrieve(self, question: str, tag_filter: List[str] = None) -> List[Dict]:
        """Return the top hits as ``[{"payload": ..., "score": ...}, ...]``,
        optionally scoped to documents carrying any of ``tag_filter``.

        Two signals extend the global top-k pool — strictly additively, since a
        signal miss must never make a document unfindable when plain chunk
        search ranks it well (a hard summary filter measurably regressed):

        - document summaries: chunks from files whose summary matches the query;
        - aggregate intent: the best chunk(s) per document via grouped search,
          so roll-up questions cover every relevant document.

        Finally, hits scoring more than ``score_margin`` below the best hit are
        dropped (top hit always kept; 0 disables)."""
        t0 = time.perf_counter()
        query_vector = self.embedder.embed_query(question)
        embed_ms = (time.perf_counter() - t0) * 1000
        summary_hits: List[Dict] = []
        summary_ms = 0.0
        group_ms = 0.0
        candidate_files: List[str] = []
        routed_added = 0
        grouped_added = 0

        t2 = time.perf_counter()
        hits = self.store.search(query_vector, self.settings.top_k, tag_filter)
        chunk_ms = (time.perf_counter() - t2) * 1000

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
                routed = self.store.search(query_vector, self.settings.top_k, tag_filter, candidate_files)
                chunk_ms += (time.perf_counter() - t2) * 1000
                hits, routed_added = self._merge(hits, routed)

        group_limit = getattr(self.settings, "aggregate_group_limit", 0) or 0
        aggregate = group_limit > 0 and (
            bool(tag_filter) or bool(_AGGREGATE_CUES.search(question))
        )
        if aggregate:
            t3 = time.perf_counter()
            grouped = self.store.search_grouped(
                query_vector,
                group_limit,
                getattr(self.settings, "aggregate_group_size", 1) or 1,
                tag_filter,
            )
            group_ms = (time.perf_counter() - t3) * 1000
            hits, grouped_added = self._merge(hits, grouped)

        margin = getattr(self.settings, "score_margin", 0) or 0
        if hits and margin > 0:
            cutoff = hits[0]["score"] - margin
            hits = [h for h in hits if h["score"] >= cutoff]

        if self.summary_store is not None and hits:
            self._attach_summaries(hits, summary_hits)

        self._log_perf(
            stage="retrieve",
            embed_ms=round(embed_ms, 2),
            summary_ms=round(summary_ms, 2),
            chunk_ms=round(chunk_ms, 2),
            group_ms=round(group_ms, 2),
            total_ms=round((time.perf_counter() - t0) * 1000, 2),
            summary_hits=len(summary_hits),
            candidate_files=len(candidate_files),
            routed_added=routed_added,
            aggregate=aggregate,
            grouped_added=grouped_added,
            hits=len(hits),
            tag_filter=tag_filter or [],
        )
        return hits

    @staticmethod
    def build_context(hits: List[Dict]) -> str:
        """Render hits as <document> tags for the prompt. The first chunk of
        each distinct source carries a <summary> briefing line when available."""
        blocks = []
        summarized_files = set()
        for index, hit in enumerate(hits, start=1):
            payload = hit["payload"]
            filename = payload.get("filename")
            summary_line = ""
            if filename not in summarized_files:
                summarized_files.add(filename)
                summary = (payload.get("document_summary") or "").strip()
                if summary:
                    summary_line = f"<summary>{summary}</summary>\n"
            blocks.append(
                f'<document index="{index}" '
                f'source="{filename}" '
                f'page="{page_label(payload)}">\n'
                f'{summary_line}{payload.get("text", "")}\n</document>'
            )
        return "\n\n".join(blocks)

    @staticmethod
    def sources(hits: List[Dict]) -> List[Dict]:
        return [to_source(hit["payload"], hit["score"]) for hit in hits]

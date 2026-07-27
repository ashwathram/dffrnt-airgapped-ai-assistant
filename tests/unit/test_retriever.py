"""Retriever.retrieve() routing-union and margin-cut behaviour, with fakes."""

from dffrnt_assistant.config import Settings
from dffrnt_assistant.retrieval.retriever import Retriever


class FakeEmbedder:
    def embed_query(self, text):
        return [0.0] * 8


def _hit(chunk_id, filename, score):
    return {"payload": {"chunk_id": chunk_id, "filename": filename}, "score": score}


class FakeChunkStore:
    """Returns `plain` for unrestricted searches, `routed` when filenames given,
    and `grouped` from search_grouped (records that it was called)."""

    def __init__(self, plain, routed, grouped=()):
        self.plain = plain
        self.routed = routed
        self.grouped = list(grouped)
        self.grouped_calls = 0

    def search(self, query_vector, top_k, tag_filter=None, filenames=None):
        pool = self.routed if filenames else self.plain
        return list(pool[:top_k])

    def search_grouped(self, query_vector, limit, group_size=1, tag_filter=None):
        self.grouped_calls += 1
        return list(self.grouped[:limit])


class FakeSummaryStore:
    def __init__(self, hits):
        self.hits = hits

    def search(self, query_vector, top_k, tag_filter=None):
        return list(self.hits[:top_k])

    def payloads_by_filenames(self, filenames):
        return [
            h["payload"] for h in self.hits
            if h["payload"].get("filename") in set(filenames)
        ]


def _settings(margin=0.0, top_k=8):
    settings = Settings()
    settings.score_margin = margin
    settings.top_k = top_k
    return settings


def test_summary_miss_never_hides_plain_results():
    # The correct document tops plain chunk search but its summary missed the
    # summary search entirely — the old hard filter made it unfindable.
    plain = [_hit("deck::c1", "deck.pptx", 0.61), _hit("faq::c1", "faq.txt", 0.5)]
    routed = [_hit("faq::c1", "faq.txt", 0.5)]
    summaries = [_hit("faq::summary", "faq.txt", 0.55)]
    retriever = Retriever(
        FakeChunkStore(plain, routed), FakeEmbedder(), _settings(),
        summary_store=FakeSummaryStore(summaries),
    )
    hits = retriever.retrieve("when was DFFRNT founded?")
    assert hits[0]["payload"]["filename"] == "deck.pptx"


def test_routing_adds_chunks_plain_search_missed():
    plain = [_hit("a::c1", "a.docx", 0.7)]
    routed = [_hit("a::c1", "a.docx", 0.7), _hit("b::c1", "b.docx", 0.65)]
    summaries = [_hit("b::summary", "b.docx", 0.68)]
    retriever = Retriever(
        FakeChunkStore(plain, routed), FakeEmbedder(), _settings(),
        summary_store=FakeSummaryStore(summaries),
    )
    hits = retriever.retrieve("q")
    ids = [h["payload"]["chunk_id"] for h in hits]
    assert ids == ["a::c1", "b::c1"]  # merged, deduped, score-ordered


def test_margin_cut_applies_after_union():
    plain = [_hit("a::c1", "a.docx", 0.7), _hit("c::c1", "c.docx", 0.4)]
    routed = [_hit("b::c1", "b.docx", 0.65)]
    summaries = [_hit("b::summary", "b.docx", 0.6)]
    retriever = Retriever(
        FakeChunkStore(plain, routed), FakeEmbedder(), _settings(margin=0.2),
        summary_store=FakeSummaryStore(summaries),
    )
    hits = retriever.retrieve("q")
    ids = [h["payload"]["chunk_id"] for h in hits]
    assert ids == ["a::c1", "b::c1"]  # 0.4 pruned by the 0.2 margin below 0.7


def test_no_summary_store_is_plain_search():
    plain = [_hit("a::c1", "a.docx", 0.7)]
    retriever = Retriever(FakeChunkStore(plain, []), FakeEmbedder(), _settings())
    assert retriever.retrieve("What is the vacation policy?") == plain


# -- R2: aggregate grouped retrieval ----------------------------------------

def test_aggregate_cue_merges_grouped_chunks():
    plain = [_hit("a::c1", "a.docx", 0.7)]
    grouped = [_hit("a::c1", "a.docx", 0.7), _hit("b::c1", "b.docx", 0.6)]
    store = FakeChunkStore(plain, [], grouped)
    retriever = Retriever(store, FakeEmbedder(), _settings())
    hits = retriever.retrieve("What rates do all candidates charge?")
    assert store.grouped_calls == 1
    assert [h["payload"]["chunk_id"] for h in hits] == ["a::c1", "b::c1"]


def test_tag_scope_triggers_grouped_search():
    plain = [_hit("a::c1", "a.docx", 0.7)]
    store = FakeChunkStore(plain, [], [])
    retriever = Retriever(store, FakeEmbedder(), _settings())
    retriever.retrieve("What is the vacation policy?", tag_filter=["Policy"])
    assert store.grouped_calls == 1


def test_single_document_question_skips_grouped_search():
    plain = [_hit("a::c1", "a.docx", 0.7)]
    store = FakeChunkStore(plain, [], [])
    retriever = Retriever(store, FakeEmbedder(), _settings())
    retriever.retrieve("What is the vacation policy?")
    assert store.grouped_calls == 0


def test_group_limit_zero_disables_grouping():
    plain = [_hit("a::c1", "a.docx", 0.7)]
    store = FakeChunkStore(plain, [], [_hit("b::c1", "b.docx", 0.6)])
    settings = _settings()
    settings.aggregate_group_limit = 0
    retriever = Retriever(store, FakeEmbedder(), settings)
    hits = retriever.retrieve("Compare all candidates.")
    assert store.grouped_calls == 0
    assert hits == plain


# -- P1: document summaries attached to hits and surfaced in the context -----

def test_summaries_attached_to_hits_from_summary_hits():
    plain = [_hit("a::c1", "a.docx", 0.7)]
    summaries = [
        {"payload": {"chunk_id": "a::summary", "filename": "a.docx",
                     "document_summary": "Overview of A."}, "score": 0.6},
    ]
    retriever = Retriever(
        FakeChunkStore(plain, plain), FakeEmbedder(), _settings(),
        summary_store=FakeSummaryStore(summaries),
    )
    hits = retriever.retrieve("What is the vacation policy?")
    assert hits[0]["payload"]["document_summary"] == "Overview of A."


def test_summaries_fetched_for_files_missing_from_summary_hits():
    # b.docx tops chunk search but its summary missed the summary top-k;
    # the retriever must fetch it by filename instead.
    plain = [_hit("b::c1", "b.docx", 0.7)]
    summaries = [
        {"payload": {"chunk_id": "b::summary", "filename": "b.docx",
                     "document_summary": "Overview of B."}, "score": 0.1},
    ]

    class TopKMissSummaryStore(FakeSummaryStore):
        def search(self, query_vector, top_k, tag_filter=None):
            return []  # summary search misses entirely

    retriever = Retriever(
        FakeChunkStore(plain, plain), FakeEmbedder(), _settings(),
        summary_store=TopKMissSummaryStore(summaries),
    )
    hits = retriever.retrieve("What is the vacation policy?")
    assert hits[0]["payload"]["document_summary"] == "Overview of B."


def test_build_context_emits_summary_once_per_file():
    hits = [
        {"payload": {"chunk_id": "a::c1", "filename": "a.docx", "text": "one",
                     "document_summary": "Overview of A."}, "score": 0.7},
        {"payload": {"chunk_id": "a::c2", "filename": "a.docx", "text": "two",
                     "document_summary": "Overview of A."}, "score": 0.6},
        {"payload": {"chunk_id": "b::c1", "filename": "b.docx", "text": "three"},
         "score": 0.5},
    ]
    context = Retriever.build_context(hits)
    assert context.count("<summary>Overview of A.</summary>") == 1
    assert 'index="1"' in context and 'index="3"' in context
    assert "three" in context

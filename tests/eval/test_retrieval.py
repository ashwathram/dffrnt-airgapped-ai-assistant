"""Retrieval quality against the live stack (no LLM generation, so it's fast).

Asserts per-query recall, a suite-level precision floor, that the additive
routing/aggregation signals never lose to plain chunk search, and that real
prompts fit the configured context window.
"""

import pytest

from dffrnt_assistant.rag import DEFAULT_SYSTEM_PROMPT, build_prompt

from .cases import ANSWERABLE

pytestmark = pytest.mark.eval

PRECISION_AT_1_FLOOR = 0.70   # measured 0.79–0.84 on this corpus
HISTORY_TOKEN_BUDGET = 2048   # headroom for 6 history turns + a long question


def _rank(hits, expected):
    files = [h["payload"].get("filename") for h in hits]
    return next((i + 1 for i, f in enumerate(files) if f in expected), None)


@pytest.mark.parametrize("case", ANSWERABLE, ids=lambda c: c["note"])
def test_expected_document_retrieved(retriever, case):
    hits = retriever.retrieve(case["query"], case.get("tags"))
    files = {h["payload"].get("filename") for h in hits}
    assert files & case["expected"], (
        f"expected one of {sorted(case['expected'])}, retrieved {sorted(files)}"
    )


def test_precision_at_1_floor(retriever):
    top1 = 0
    for case in ANSWERABLE:
        hits = retriever.retrieve(case["query"], case.get("tags"))
        rank = _rank(hits, case["expected"])
        top1 += int(rank == 1)
        print(f"  [{'#' + str(rank) if rank else 'MISS':>4}] {case['note']}")
    p1 = top1 / len(ANSWERABLE)
    print(f"  P@1 = {top1}/{len(ANSWERABLE)} ({p1:.0%})")
    assert p1 >= PRECISION_AT_1_FLOOR


def test_routing_never_loses_to_plain_search(retriever, plain_retriever):
    """The summary-routing and aggregate-grouping signals are additive: they may
    only add evidence, so the production retriever must never rank an expected
    document worse than plain chunk search does."""
    regressions = []
    for case in ANSWERABLE:
        routed = _rank(retriever.retrieve(case["query"], case.get("tags")), case["expected"])
        plain = _rank(plain_retriever.retrieve(case["query"], case.get("tags")), case["expected"])
        flag = "" if (routed or 99) <= (plain or 99) else "  <-- REGRESSION"
        print(f"  routed #{routed or '-'}  plain #{plain or '-'}  {case['note']}{flag}")
        if flag:
            regressions.append(case["note"])
    assert not regressions


def test_prompts_fit_context_window(retriever, settings):
    """Ollama silently truncates prompts beyond num_ctx; the retrieved context
    plus history headroom must stay inside it (tokens estimated as chars/4)."""
    system_prompt = settings.system_prompt or DEFAULT_SYSTEM_PROMPT
    worst = 0
    for case in ANSWERABLE:
        hits = retriever.retrieve(case["query"], case.get("tags"))
        prompt = build_prompt(system_prompt, retriever.build_context(hits), "", case["query"])
        worst = max(worst, len(prompt) // 4)
    print(f"  largest prompt ~{worst} tokens of num_ctx={settings.llm_num_ctx}")
    assert worst + HISTORY_TOKEN_BUDGET <= settings.llm_num_ctx

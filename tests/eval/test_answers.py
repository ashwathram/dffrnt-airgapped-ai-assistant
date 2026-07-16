"""End-to-end answer quality: retrieve -> prompt -> generate, scored on the
generated text. Every case is a full local-LLM generation, so a complete run
takes a while with a large model.

  correctness  answer contains the expected facts (must_include groups)
  citation     answer carries at least one inline [n] marker
  refusal      out-of-KB negatives and the tag-isolation probe must refuse
"""

import re

import pytest

from .cases import CASES, NEGATIVE_CASES, REFUSAL_PHRASE, TAG_CASES

pytestmark = pytest.mark.eval

CORRECTNESS_FLOOR = 0.75  # measured 0.84 on this corpus
CITATION_FLOOR = 0.90     # measured 1.00

_CITE = re.compile(r"\[\d+\]")


def _answer(pipeline, case) -> str:
    return pipeline.answer(case["query"], None, case.get("tags"))["answer"]


def _meets(answer: str, groups) -> bool:
    low = answer.lower()
    return all(any(opt.lower() in low for opt in group) for group in groups)


def test_grounded_answers_are_correct_and_cited(pipeline):
    scored = [
        c for c in CASES + TAG_CASES
        if not c.get("expect_refusal") and not c.get("checks", {}).get("informational")
    ]
    correct = cited = 0
    for case in scored:
        answer = _answer(pipeline, case)
        ok = _meets(answer, case["checks"]["must_include"])
        cite = bool(_CITE.search(answer))
        correct += int(ok)
        cited += int(cite)
        print(f"  [{'PASS' if ok and cite else 'FAIL'}] correct={'Y' if ok else 'N'} "
              f"cite={'Y' if cite else 'N'}  {case['note']}")
    n = len(scored)
    print(f"  correctness {correct}/{n} ({correct / n:.0%})  citation {cited}/{n} ({cited / n:.0%})")
    assert correct / n >= CORRECTNESS_FLOOR
    assert cited / n >= CITATION_FLOOR


_REFUSALS = [c for c in TAG_CASES if c.get("expect_refusal")] + NEGATIVE_CASES


@pytest.mark.parametrize("case", _REFUSALS, ids=lambda c: c["note"])
def test_out_of_scope_queries_refuse(pipeline, case):
    """Anti-hallucination guard: the canonical refusal sentence, never a made-up
    answer, for questions the documents cannot support."""
    answer = _answer(pipeline, case)
    assert REFUSAL_PHRASE in answer.lower(), f"expected refusal, got: {answer[:200]}"

"""Evaluation queries grounded in the synthetic corpus (eval/gen_corpus.py).

Every fact in ``must_include`` appears verbatim in exactly one corpus document
(or a deliberately controlled set of them), so correctness scoring is
unambiguous — the corpus was written for these checks, not the other way round.

Case fields:
  query        : the user question
  expected     : filename(s) that should be retrieved (used by eval/rag_eval.py)
  task         : resume-hr | proposal-corr | knowledge-base  (reporting axis)
  checks       : must_include — list of groups; every group must be satisfied,
                 a group is satisfied by ANY of its case-insensitive substrings.
                 informational — record behaviour but exclude from correctness.
  tags         : optional tag filter, exercises the tag-scoped retrieval path.
  expect_refusal : the correct behaviour is the canonical refusal sentence
                 (used for tag-isolation cases where the answer is out of scope).

NEGATIVE_CASES are outside the corpus; a faithful assistant must refuse with the
canonical sentence, never fabricate.
"""

# Canonical refusal substring (from the system prompt's mandated sentence).
REFUSAL_PHRASE = "do not contain enough information"

CASES = [
    # ------------------------------------------------------------------
    # Task 1 — resumes / HR extraction and aggregation
    # ------------------------------------------------------------------
    {
        "query": "What is Amara Okafor's work experience?",
        "expected": {"resume-amara-okafor.docx"},
        "task": "resume-hr",
        "note": "single-resume experience extraction",
        "checks": {"must_include": [
            ["lumen digital"], ["craft&pixel", "craft & pixel"], ["nps"],
        ]},
    },
    {
        "query": "Summarize Ben Tremblay's experience as a UI developer.",
        "expected": {"resume-ben-tremblay.docx"},
        "task": "resume-hr",
        "note": "single-resume summary",
        "checks": {"must_include": [
            ["nova interfaces"], ["hydro-qu", "hydro qu"], ["react"],
        ]},
    },
    {
        "query": "What did Chloe Nguyen achieve at MapleSoft Insights?",
        "expected": {"resume-chloe-nguyen.pdf"},
        "task": "resume-hr",
        "note": "single-resume achievement (PDF loader)",
        "checks": {"must_include": [
            ["88%", "88 %", "from 62"], ["usability", "task success"],
        ]},
    },
    {
        "query": "Which candidates are proficient in Figma?",
        "expected": {"resume-amara-okafor.docx", "resume-diego-ramirez.txt"},
        "task": "resume-hr",
        "note": "multi-resume aggregation (Figma = Okafor + Ramirez only)",
        "checks": {"must_include": [["okafor", "amara"], ["ramirez", "diego"]]},
    },
    {
        "query": "What hourly rates do our contract candidates charge, and who is the most expensive?",
        "expected": {
            "contractor-roster.xlsx", "resume-amara-okafor.docx",
            "resume-ben-tremblay.docx", "resume-chloe-nguyen.pdf",
            "resume-diego-ramirez.txt", "resume-elena-petrova.docx",
        },
        "task": "resume-hr",
        "note": "rate roll-up across resumes/roster (max = Petrova $105)",
        "checks": {"must_include": [["105"], ["petrova", "elena"]]},
    },
    {
        "query": "Who has experience with government or public-sector service design?",
        "expected": {"resume-elena-petrova.docx"},
        "task": "resume-hr",
        "note": "semantic match on experience domain",
        "checks": {"must_include": [["petrova", "elena"], ["permit", "govconnect"]]},
    },
    {
        "query": "Is Elena Petrova's hourly rate within our approved senior contractor band?",
        "expected": {"resume-elena-petrova.docx", "policy-contractor-onboarding.md",
                     "contractor-roster.xlsx"},
        "task": "resume-hr",
        "note": "cross-document reasoning (rate $105 vs senior band $90–120)",
        "checks": {"must_include": [["105"], ["120"]]},
    },
    # ------------------------------------------------------------------
    # Task 2 — proposals and correspondence
    # ------------------------------------------------------------------
    {
        "query": "What are the budget and timeline for the Aurora Health patient portal proposal?",
        "expected": {"proposal-aurora-patient-portal.docx"},
        "task": "proposal-corr",
        "note": "proposal fact lookup",
        "checks": {"must_include": [["240,000", "240000", "$240"], ["16 week", "16-week"]]},
    },
    {
        "query": "Summarize the Aurora Health patient portal proposal.",
        "expected": {"proposal-aurora-patient-portal.docx"},
        "task": "proposal-corr",
        "note": "proposal summary",
        "checks": {"must_include": [
            ["aurora"], ["portal"], ["design system", "prototype", "accessibility"],
        ]},
    },
    {
        "query": "What deliverables does the Borealis rebrand proposal include?",
        "expected": {"proposal-borealis-rebrand.md"},
        "task": "proposal-corr",
        "note": "proposal deliverables list",
        "checks": {"must_include": [["logo"], ["style guide"], ["template"]]},
    },
    {
        "query": "Did Aurora Health ask to change the project timeline, and what was agreed?",
        "expected": {"correspondence-aurora-timeline.txt"},
        "task": "proposal-corr",
        "note": "correspondence outcome (12 weeks @ $258k agreed 2026-03-14)",
        "checks": {"must_include": [
            ["12 week", "12-week"], ["258,000", "258000", "$258", "18,000", "18000"],
        ]},
    },
    # ------------------------------------------------------------------
    # Task 3 — internal knowledge base
    # ------------------------------------------------------------------
    {
        "query": "What are the approved hourly rate bands for contractors?",
        "expected": {"policy-contractor-onboarding.md"},
        "task": "knowledge-base",
        "note": "policy numeric bands",
        "checks": {"must_include": [["60"], ["90"], ["120"]]},
    },
    {
        "query": "How quickly must contractor screening be completed, and what is required?",
        "expected": {"policy-contractor-onboarding.md"},
        "task": "knowledge-base",
        "note": "policy process detail",
        "checks": {"must_include": [["10 business days"], ["nda"]]},
    },
    {
        "query": "What professional development budget do employees get each year?",
        "expected": {"policy-benefits-summary.docx"},
        "task": "knowledge-base",
        "note": "benefits figure lookup",
        "checks": {"must_include": [["1,800", "1800"]]},
    },
    {
        "query": "Does the AI assistant send any client data to the cloud?",
        "expected": {"faq-security-airgap.txt"},
        "task": "knowledge-base",
        "note": "security FAQ (executive interrogation)",
        "checks": {"must_include": [["on-prem", "locally", "air-gap", "airgap", "no internet"]]},
    },
    {
        "query": "When was DFFRNT founded and how many employees does it have?",
        "expected": {"capabilities-overview.pptx"},
        "task": "knowledge-base",
        "note": "company facts (PPTX loader)",
        "checks": {"must_include": [["2015"], ["38"]]},
    },
    # ------------------------------------------------------------------
    # Known-limit probe: tabular aggregation over the CSV
    # ------------------------------------------------------------------
    {
        "query": "How many total hours were logged on Aurora Discovery in Q1 2026?",
        "expected": {"project-hours-q1-2026.csv"},
        "task": "knowledge-base",
        "note": "tabular aggregation (sum 112+118+121+96=447) — informational",
        "checks": {"informational": True},
    },
]

# Tag-scoped cases: the same retrieval path with a tags filter, as the UI sends.
# The last case is an isolation probe: the true answer lives OUTSIDE the scoped
# tag, so the assistant must refuse rather than leak or fabricate.
TAG_CASES = [
    {
        "query": "Which candidate holds a PhD?",
        "tags": ["Resume"],
        "expected": {"resume-chloe-nguyen.pdf"},
        "task": "resume-hr",
        "note": "tag-scoped resume search",
        "checks": {"must_include": [["nguyen", "chloe"]]},
    },
    {
        "query": "What is the base vacation allowance?",
        "tags": ["Policy"],
        "expected": {"policy-benefits-summary.docx"},
        "task": "knowledge-base",
        "note": "tag-scoped policy lookup",
        "checks": {"must_include": [["4 weeks", "four weeks"]]},
    },
    {
        "query": "What hourly rate does Amara Okafor charge?",
        "tags": ["Proposal"],
        "expected": set(),
        "task": "resume-hr",
        "note": "tag isolation — answer exists only outside the scoped tag",
        "expect_refusal": True,
        "checks": {},
    },
]

# Clearly outside the corpus — a faithful assistant must refuse, not fabricate.
NEGATIVE_CASES = [
    {"query": "What is the capital of Australia?", "note": "general knowledge, not in KB"},
    {"query": "What was the Adecco Group's revenue in 2025?",
     "note": "was in the OLD corpus, absent now — stale-memory fabrication probe"},
    {"query": "What is DFFRNT's current share price?",
     "note": "plausible-sounding internal fact that no document contains"},
    {"query": "Summarize the plot of the film Inception.", "note": "pop culture, not in KB"},
]

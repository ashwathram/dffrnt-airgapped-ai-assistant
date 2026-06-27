"""Sample queries for RAG hyperparameter tuning, grounded in the live KB.

Each case names the document(s) that should answer it (``expected``, used by
eval/rag_eval.py) and, where the corpus gives solid ground truth, answer-quality
checks (``checks``, used by eval/answer_eval.py):

  must_include : list of groups; every group must be satisfied and a group is
                 satisfied when the answer contains ANY of its (case-insensitive)
                 substrings. Facts here were read off the actual chunk text, not
                 the model's output. Some thematic queries use loose topical
                 groups on purpose — the goal is regression/▵-detection between
                 generation settings, not a perfect grader.
  cite         : answer should carry at least one [n] citation (default True).

NEGATIVE_CASES are clearly outside this KB; a faithful assistant must refuse with
the canonical sentence (see REFUSAL_PHRASE), never fabricate. These test the
anti-hallucination guard directly.
"""

# Canonical refusal substring (from the system prompt's mandated sentence).
REFUSAL_PHRASE = "do not contain enough information"

CASES = [
    {
        "query": "What was the Adecco Group's revenue in 2025?",
        "expected": {"the-adecco-group-annual-report-2025.pdf"},
        "note": "annual-report figure lookup",
        "checks": {"must_include": [["23,082", "23082", "23.1 billion", "23.08"]]},
    },
    {
        "query": "How many people does the Adecco Group employ and where does it operate?",
        "expected": {"the-adecco-group-annual-report-2025.pdf"},
        "note": "annual-report headcount / footprint",
        # The report carries several valid headcount framings (169,000 colleagues,
        # 34,000 FTE company-based, …) — verified in the corpus. Accept any
        # documented figure rather than pin one, plus the operating footprint.
        "checks": {"must_include": [
            ["169,000", "34,000", "company-based", "colleagues", "fte"],
            ["countries", "62", "60"],
        ]},
    },
    {
        "query": "What are the main priorities CEOs have for AI according to the C-suite study?",
        "expected": {"2026-ceo-study-rewiring-the-c-suite-report.pdf"},
        "note": "CEO study thematic (loose topical)",
        "checks": {"must_include": [
            ["AI", "artificial intelligence"],
            ["c-suite", "flywheel", "agent", "initiative", "priorit", "transformation"],
        ]},
    },
    {
        "query": "Summarize Kartoza's technical proposal for the challenge fund.",
        "expected": {"challengefund3-technicalproposal-kartoza.pdf"},
        "note": "proposal summary",
        "checks": {"must_include": [
            ["kartoza"],
            ["red cross", "climate centre", "climate"],
        ]},
    },
    {
        "query": "Which geospatial or GIS technologies does the Kartoza proposal rely on?",
        "expected": {"challengefund3-technicalproposal-kartoza.pdf"},
        "note": "proposal technical detail",
        "checks": {"must_include": [
            ["foss", "open source", "open-source", "gis", "geospatial", "qgis", "postgis"],
        ]},
    },
    {
        "query": "What is the candidate's work experience as a software engineer?",
        "expected": {"Resume-Sample-1-Software-Engineer.pdf"},
        "note": "resume experience",
        "checks": {"must_include": [
            ["software engineer", "application development", "automation", "web application"],
        ]},
    },
    {
        "query": "Which programming languages and tools does the software engineer candidate know?",
        "expected": {"Resume-Sample-1-Software-Engineer.pdf"},
        "note": "resume skills",
        "checks": {"must_include": [["c#", "c++", "visual basic", "cuda"]]},
    },
    {
        "query": "What does the McKinsey report recommend for digital transformation?",
        "expected": {"dmava_mckinseyco.pdf"},
        "note": "McKinsey thematic (loose topical)",
        "checks": {"must_include": [
            ["mckinsey", "leadership", "transformation", "capability", "design", "coach"],
        ]},
    },
    {
        "query": "Which product category and region had the highest sales in the Superstore data?",
        "expected": {"Sample - Superstore.csv"},
        "note": "tabular aggregation — beyond chunk-RAG; informational only",
        # No must_include: correctly aggregating over 4,787 row-chunks is outside
        # what retrieval-augmented generation can do here. We only record whether
        # it answered/refused/cited, and exclude it from the correctness rate.
        "checks": {"informational": True},
    },
    {
        "query": "Show me the structure of a problem, solution and impact case study.",
        "expected": {
            "IC-Problem-Solution-Impact-Case-Study-Template-for-Powerpoint-Example_Powerpoint.pptx",
            "IC-One-Page-Case-Study-Template-for-Microsoft-Word-Example_WORD.docx",
            "IC-Data-Driven-Case-Study-Template-Example.xlsx",
            "IC-Data-Driven-Case-Study-Template-Example_WORD.docx",
            "PHE-case-study-ppt.Final_.pptx",
        },
        "note": "case-study template (loose topical)",
        "checks": {"must_include": [
            ["problem", "solution", "impact", "case study", "result", "outcome"],
        ]},
    },
    {
        "query": "What measurable impact and results does the PHE case study report?",
        "expected": {"PHE-case-study-ppt.Final_.pptx"},
        "note": "case-study outcome (loose topical)",
        "checks": {"must_include": [
            ["case study", "practice", "health", "reflection", "revalidation", "impact"],
        ]},
    },
]

# Clearly outside the corpus — a faithful assistant must refuse, not fabricate.
NEGATIVE_CASES = [
    {"query": "What is the capital of Australia?", "note": "general knowledge, not in KB"},
    {"query": "What were Apple's iPhone unit sales in Q4 2024?", "note": "external company, not in KB"},
    {"query": "Summarize the plot of the film Inception.", "note": "pop culture, not in KB"},
]

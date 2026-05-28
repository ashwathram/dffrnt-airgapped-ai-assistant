
# Project Prompt & Implementation Guide

Purpose
Build the ingestion, embedding, chunking, Qdrant indexing, retrieval, and evaluation pipeline for an offline RAG knowledge assistant.

Scope ownership ends at:

Question
↓
Retrieval
↓
Selected evidence package

This scope does NOT include:

- chat UI
- session management
- multi-turn memory
- frontend
- authentication
- final LLM response rendering

The pipeline should expose evidence and metadata so downstream systems can generate answers.

====================================================
Core Goal
====================================================

Users should ask natural questions without specifying files.

System behavior:

Many files
↓
Chunk independently
↓
Search whole knowledge base
↓
Retrieve candidate evidence
↓
Filter
↓
Rerank
↓
Balance evidence across files
↓
Return structured evidence package

The system should retrieve information across all relevant files rather than behave as a single-document search tool.


====================================================
1. Multi-file ingestion
====================================================

Default:

Scan:

database/raw/

recursively.

Supported:

PDF
DOCX
PPTX
CSV
TXT
MD

Process every file independently.

IMPORTANT:

Never merge text from different files into one chunk.

Bad:

Healthcare experience Hospital AI projects

Good:

proposal.pdf → chunk_A1
resume.docx → chunk_B1

Cross-file relationships happen during retrieval.

Chunk IDs:

filename::section::chunk_number

Example:

proposal.pdf::healthcare::chunk_2


====================================================
2. Chunk metadata
====================================================

Store metadata for every chunk:

{
source_file,
document_title,
filename,
file_type,
chunk_id,
page_number,
slide_index,
char_start,
char_end,
section_heading,
chunk_text,

additional_metadata:{
department,
role,
confidential,
tags
}
}

Metadata must support:

- source tracing
- downstream citations
- metadata filtering
- access filtering
- evidence analysis


====================================================
3. Chunking strategies
====================================================

Support:

fixed
sentence
paragraph
recursive
semantic

Default:

recursive

Recursive flow:

heading
↓
section
↓
paragraph
↓
sentence
↓
character fallback

Use overlap:

100–200

Chunk size:

800–1200

Chunking happens independently inside each file.

Do not split meaningful sections unnecessarily.


====================================================
4. Chunking evaluation
====================================================

Compare:

fixed
sentence
paragraph
recursive
semantic

For each strategy:

Ingest ALL files
↓
run retrieval evaluation
↓
compare metrics

Metrics:

Recall@K
Precision@K
MRR
Coverage

Select best-performing strategy.


====================================================
5. Hybrid retrieval pipeline
====================================================

Do NOT use:

top_k=3

Retrieval flow:

User question
↓
query embedding
↓
vector retrieval
↓
optional BM25 retrieval
↓
merge candidates
↓
threshold filtering
↓
exact duplicate removal
↓
optional reranking
↓
balanced source selection
↓
return evidence package

Suggested:

candidate_top_k:

30–50


Similarity threshold:

configurable

Suggested tuning range:

0.75–0.85

Threshold values must be selected experimentally.


====================================================
6. Duplicate handling
====================================================

Remove:

exact duplicates only

Do NOT remove:

semantically similar chunks from different files

Preserve:

cross-document evidence diversity


Bad:

proposal.pdf removed because resume.pdf discussed similar content

Good:

proposal.pdf
resume.pdf
case_study.pdf

all preserved


====================================================
7. Evidence selection
====================================================

Do not use:

fixed context_chunk_limit

Evidence selection should depend on:

- similarity score
- keyword score
- reranker score
- source diversity
- context token budget
- retrieval distribution

Avoid source dominance.

Bad:

proposal.pdf x10

Better:

proposal.pdf x3
resume.docx x3
case_study.pdf x2
sales.txt x2


====================================================
8. Business-focused evaluation questions
====================================================

Do NOT generate:

first 12 words of chunks

Do NOT generate:

random factual extraction questions

Generate:

20–30 business-critical questions across the corpus

Primary categories:

Resume retrieval:

Find healthcare consulting experience

Find resumes mentioning proposal work

Find AI implementation experience

Proposal generation:

Find proposal examples

Find similar project proposals

Find proposal templates

Case studies:

Find similar implementations

Find project outcomes

Find healthcare examples

Sales:

Find historical sales content

Find AI messaging examples

Find sales materials

Knowledge lookup:

Which projects use RAG?

Which projects mention air-gapped deployment?

Generate:

1–3 paraphrased versions per question


Store:

{
query:
"Find healthcare AI experience",

expected_chunk_ids:[
chunk12,
chunk55,
chunk91
],

expected_source_files:[
proposal.pdf,
resume.docx,
case_study.pdf
],

type:"summary"
}


====================================================
9. Retrieval evaluation
====================================================

Allow:

multiple correct chunks

Measure:

Recall@K

Precision@K

MRR

Coverage

Threshold recall

Success:

retrieved evidence includes:

expected chunks

OR

expected source coverage


====================================================
10. Evidence strength signals
====================================================

Compute:

max_score

avg_score

num_candidates_above_threshold

coverage_count

If evidence weak:

flag retrieval quality

Return:

evidence_strength metrics

These support downstream hallucination safeguards.


====================================================
11. Retrieval output package
====================================================

Return structured evidence:

{
query,

retrieved_chunks:[
{
chunk_text,
source_file,
page_number,
score,
chunk_id
}
],

evidence_strength:{

max_score,
avg_score,
coverage_count
}
}

Downstream systems should be able to:

- cite evidence
- synthesize across files
- detect weak retrieval


====================================================
12. Offline requirements
====================================================

No external API usage.

Support:

local embedding models

local Qdrant

local rerankers

local LLM integration later


====================================================
13. Configuration
====================================================

source_folder

chunking_method

chunk_size

overlap

candidate_top_k

similarity_threshold

use_reranker

use_hybrid

eval_count

artifact_directory

metadata_filter

evidence_threshold


====================================================
Acceptance Criteria
====================================================

Default runs:

scan database/raw

Retrieval:

returns evidence from multiple files when relevant

Evaluation:

produces Recall@K
Precision@K
MRR
Coverage

Cross-file retrieval test:

Question:

Find healthcare AI experience

Expected evidence:

proposal.pdf
resume.docx
case_study.pdf

Retrieved evidence should contain multiple source files.
can you use this, and remove original? 

CI / Automation suggestions
*- Add a GitHub Actions job to:
  - Create a venv and install pinned dependencies from `requirements.txt` (or use a wheelhouse for air-gapped installs).
  - Start a Qdrant service (Docker) or use a lightweight in-memory mock for vector store in CI.
  - Run a small reproducible eval (1–5 documents) that exercises ingestion → chunking → embedding → retrieval → generation, and fail the job when recall@k or coverage drops below a configured threshold.
  - Persist artifacts (JSON/CSV) that contain per-query expected chunk lists, retrieved chunk lists, and computed metrics for trend tracking.

Design notes and integration guidance
-- Multi-file ingestion
  - Default behavior: scan the configured `source_folder` recursively and ingest every supported file unless `--source` narrows the scope.
  - Supported types: PDF, DOCX, PPTX, CSV, TXT, MD. Each loader must return structured data including `text`, `file_type`, `filename`, `document_title` (if available), page numbers or slide indices, and a best-effort mapping of section headings.
  - Chunk each file independently and generate a deterministic `chunk_id` that encodes `filename` + `section` + `offset` (e.g., `NCT061_sample.pdf::sec-3::chunk-2`).

-- Chunk metadata (stored for every chunk)
  - `source_file`: workspace-relative path under `database/raw/`.
  - `document_title` or `filename`.
  - `file_type` (pdf/docx/pptx/csv/txt/md).
  - `chunk_id` (unique per-chunk).
  - `page_number` or `slide_index` (when available; else null).
  - `char_start` / `char_end` (byte/char offsets into the source text for traceability).
  - `section_heading` (best-effort, null when unavailable).
  - `chunk_text` (the text stored with the chunk; also indexed/passed to the LLM when generating answers).

-- Hybrid retrieval & selection flow (recommended implementation)
 1. User question → create query embedding using `src/embeddings/embedder.py`.
 2. Vector search: retrieve `top_k_candidate` (configurable, e.g., 30–50) across all collections/indices.
 3. Optional keyword/BM25 pass: run a text-based retrieval on the corpus and union results with vector candidates.
 4. Apply similarity threshold (configurable, e.g., `score >= 0.80`) to filter weak matches. If too few remain, relax threshold or fall back to top-N candidates.
 5. Deduplicate near-identical chunks (e.g., Jaccard or cosine on text/embeddings) and collapse duplicates, keeping the chunk with highest score.
 6. Group preserved chunks by `source_file` for coverage reporting.
 7. Optional reranking: use a lightweight reranker or call the LLM with a relevance prompt to rerank the candidate set.
 8. Final selection: pick the highest-scoring chunks that fit within the LLM context budget (configurable `context_chunk_limit`); prefer balanced coverage across relevant files when multiple documents contribute evidence.
 9. Pass the selected chunks (with metadata) to the LLM generator.

-- Reranking & LLM-based scoring (optional)
  - Provide a toggle `--use-reranker`. When enabled, rerank the candidate set using a neural reranker or an LLM scoring prompt that compares the query to each chunk and returns a relevance score.
  - Reranking is valuable when many domain-specific synonyms exist or when short chunks yield noisy similarity scores.

-- Answer generation behavior
  - Feed the selected chunks (ordered by relevance) into the LLM prompt as evidence. Include `source_file` and `page_number` inline for each chunk so the model can cite sources.
  - The LLM prompt should instruct the model to: 1) synthesize across chunks and files, 2) explicitly cite source filenames and page numbers for factual claims, 3) indicate uncertainty when evidence is weak or below threshold, and 4) avoid inventing facts beyond provided evidence.
  - If retrieved context does not meet configured thresholds (few chunks or low similarity), the assistant should reply that it cannot find strong evidence and optionally list likely sources to check.

-- Evaluation improvements
  - Replace slice-based query generation with a question generator that produces 1–3 paraphrased, realistic questions per chunk/section. Store evaluation items as:

```json
{
  "query": "What healthcare AI projects has the company worked on?",
  "expected_chunk_ids": ["fileA_chunk_12","fileB_chunk_7"],
  "expected_source_files": ["fileA.pdf","fileB.docx"],
  "type": "summary"
}
```

  - Evaluation harness should compute recall@k, precision@k, MRR, and coverage per query and aggregate across the corpus and per-file.
  - Store per-query artifacts (retrieved chunk IDs, scores, final selected chunks, generation output) in `artifacts/eval/YYYYMMDD_{run}.json` for auditability.

-- Configuration (CLI flags / config file)
  - `--source` : source folder to ingest (default: `database/raw`).
  - `--chunking-method` : `recursive|sentence|paragraph|fixed` (default: `recursive`).
  - `--chunk-size` : target chunk size (tokens or chars, default 1000).
  - `--overlap` : overlap size (default 150).
  - `--top-k-candidate` : initial candidate vector search size (default 50).
  - `--similarity-threshold` : float in [0,1] to filter candidates (default 0.8).
  - `--context-chunk-limit` : maximum chunks to include in LLM prompt (default 12, but depends on model context window).
  - `--use-reranker` : boolean toggle for reranking stage.
  - `--use-hybrid` : enable BM25/keyword + vector hybrid search.
  - `--eval-count` : number of generated evaluation queries per document/section.
  - `--artifacts-dir` : where to write evaluation artifacts and reports.

Example run (limited folder, hybrid retrieval, rerank enabled):

```powershell
python scripts/semantic_search_demo.py --source "database/raw/Client_Related" --chunking-method recursive --chunk-size 1000 --overlap 150 --top-k-candidate 50 --similarity-threshold 0.80 --use-hybrid True --use-reranker True --eval-count 20
```

Implementation notes for engineers
- Update `src/ingestion/loaders.py` to ensure each loader returns page and heading metadata when available. For CSV/TSV, treat rows or logical sections as sections.
- Extend `src/processing/chunker.py` to implement the recursive structure-aware algorithm and to emit the metadata fields listed above.
- Extend `src/vector_store/qdrant_store.py` (or wrapper) to:
  - support retrieving `top_k_candidate` and returning both vector scores and payload metadata,
  - support filtering by a score threshold,
  - optionally accept a list of doc-level BM25 candidate IDs to union with vector candidates (the demo harness can run an internal BM25 index based on chunk_text).
- Update `scripts/semantic_search_demo.py` to:
  - ingest multiple files automatically when `--source` points to a folder,
  - produce evaluation artifacts in JSON/CSV format with per-query expectations and results,
  - implement the hybrid retrieval → dedup → rerank → select flow described above.

Acceptance criteria
- Default runs should scan `database/raw` and produce per-query artifacts in `artifacts/eval/`.
- Retrieval should return candidate sets spanning multiple files when relevant and generate answers citing multiple sources.
- Evaluation metrics (recall@k, precision@k, coverage) should be available per run and per-file.
- The system should be configurable via CLI flags or a small YAML/JSON config file.

---

If you'd like, I can now:
- implement the documented CLI flags in `scripts/semantic_search_demo.py` and wire them to the new retrieval flow,
- update `src/processing/chunker.py` with the recursive/structure-aware chunker,
- or add the BM25 hybrid component and evaluations harness code.
Tell me which of these to implement first and I'll proceed.

Downstream chat & safety features (cite, filter, avoid hallucination, offline)

- Purpose: ensure the chat frontend can safely synthesize answers across multiple files, cite evidence, allow metadata filtering, detect weak retrievals, and operate fully offline.

- Cite sources using stored metadata
  - Always pass `source_file`, `document_title`/`filename`, and `page_number`/`slide_index` with each selected chunk into the generation prompt.
  - Formatting recommendation for model instructions: include inline citation tokens next to each chunk, e.g. `[source: proposal.pdf | page:2]` or `[[proposal.pdf::page2]]`, and instruct the model to include citations for claims.
  - Example generator input snippet passed to LLM:

```
Evidence 1: [proposal.pdf | page 2] "...text..."
Evidence 2: [resume.docx | page 4] "...text..."

Question: What healthcare AI projects has the company worked on?

Instructions: Synthesize evidence from the passages above. For every factual claim cite evidence using the [filename | page] tag. If no strong evidence exists, respond that the system could not find sufficient evidence.
```

- Metadata filtering and role-based filters
  - Store arbitrary metadata keys with each chunk payload (e.g., `role: author`, `department: sales`, `confidential: true`) so downstream chat can filter or prioritize evidence at query time.
  - Add CLI/SDK flags such as `--metadata-filter "role:author"` or `--metadata-filter "department:sales"` to limit candidate retrieval to chunks matching metadata.
  - Implementation note: ensure the vector store wrapper supports metadata filters at search time (Qdrant supports `filter` payloads) and the hybrid candidate union respects those filters.

- Hallucination detection and weak-evidence handling
  - Compute simple evidence-strength signals before generation:
    - `max_score` and `avg_score` among selected candidate embeddings
    - `num_candidates_above_threshold`
    - `coverage_count` (number of distinct source files represented)
  - Configure `--evidence-threshold` (default around 0.75) and `--min_evidence_files` (default 1). If `max_score` < threshold or `num_candidates_above_threshold` is low, mark retrieval as weak.
  - Generation policy when evidence is weak:
    - Do not allow confident assertions. Start with an explicit disclaimer: "I could not find strong evidence for that claim in the knowledge base. Here are the closest matches: ..."
    - Optionally include retrieved passages and their scores so users can verify.
  - Reranker-based verification: when enabled, ask the reranker/LLM to produce a binary `supports_query` label per claim against each chunk to further detect unsupported hallucinations.

- Retrieval across all documents by default
  - Default `--source` is `database/raw` and the ingestion pipeline indexes all supported files. Queries run across the entire index unless `--source` or `--metadata-filter` restricts scope.

- Fully offline operation
  - The system must not call external APIs by default. Add configuration options:
    - `--offline True` or `--model-path /path/to/local/model` to force local LLM use.
    - `--no-telemetry` to disable any outgoing network calls from evaluation tooling.
  - Document how to plug a local LLM: path, model type, tokenizer; ensure the generator code can accept a pluggable local model interface (e.g., function `generate(prompt, max_tokens, temperature, model_path)`).

- Configuration flags (additions)
  - `--metadata-filter` : key:value filter to restrict candidate retrieval by payload metadata.
  - `--evidence-threshold` : float threshold for weak vs strong evidence (default 0.75).
  - `--min-evidence-files` : minimum distinct source files to consider answer adequately supported (default 1).
  - `--model-path` : path to a local LLM binary or local server endpoint (for offline runs).
  - `--offline` : boolean to enforce offline-only behavior.

Implementation notes
- Update `src/vector_store/qdrant_store.py` wrappers to accept a `filter` argument and return payload metadata with each search result.
- Update ingestion to ensure flexible payloads (allow `role`, `department`, `confidential` etc.) and deterministic `chunk_id` scheme.
- Update `scripts/semantic_search_demo.py` to produce `artifacts/eval/` entries that record `evidence_strength` signals and include them in reports.
- Update generation prompt templates in the demo to include evidence passages with citation tags and explicit failure/disclaimer instructions when evidence is weak.

Acceptance criteria (additional)
- Chat output includes inline citations for claims when evidence exists.
- The system flags weak retrievals and returns a cautious response rather than hallucinated assertions.
- Metadata filters work end-to-end (ingest → index → filtered retrieval) and are exposed on CLI.
- Offline mode documented and runnable with a local LLM configured via `--model-path`.


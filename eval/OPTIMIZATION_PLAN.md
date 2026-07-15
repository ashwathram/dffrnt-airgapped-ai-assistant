# RAG Optimization Analysis & Plan — 2026-07-14

**Branch:** `dev-prototype` @ `ef60aa3` · **Method:** live re-measurement with the `eval/` harness
(retrieval sweep, summary-routing A/B, chunk health, end-to-end answer eval), all against the
running Docker stack (qwen3:30b-a3b + bge-m3 + Qdrant).

Companion to `eval/EVALUATION_REPORT.md` (2026-07-05). That report's two headline recommendations
— chunk packing and document summaries — were implemented in PR #7 (`update_RAG`) *after* the
report, but had never been re-measured. This document measures them, identifies one regression
and several gaps, and plans the next optimization round around the three intended use cases:

1. **Per-document LLM summaries in metadata** for better context impressions.
2. **System-prompt laxness** — answer more willingly (esp. tabular/derived summaries) while
   keeping the citation format and anti-fabrication guarantees.
3. **RFP / team-resume generation readiness** — aggregate a set of resumes into a standard
   team document, optionally amending a document supplied in the prompt.

---

## 1. What was measured today

### 1.1 The live KB was stale — the PR #7 improvements had never reached the data

The live collection still held the **2026-07-05 ingest** (75 fragmented chunks for the 14 eval
docs; median 108 chars, 48% under 100 chars) and the summary collection was **empty (0 points)**,
so the new summary-routing code path had never executed in production. Everything below was
measured after force re-uploading the 14 eval-corpus documents through the live `/api/upload`
(no other documents touched; the KB also contains two non-corpus user documents,
`Resume-Sample-1-Software-Engineer.pdf` and `Sample - Superstore.csv` @ 1,536 chunks, which act
as realistic distractors).

### 1.2 Chunk packing (`chunk_floor=128`) — confirmed, large win

| Metric (14 eval docs) | Old ingest | Re-ingest (floor=128) |
|---|---|---|
| Chunks | 75 | **47** |
| Median chunk chars | 108 | **179** |
| p10 chunk chars | 14 | **126** |
| Chunks < 30 chars | 17.3% | **0%** |
| Chunks < 100 chars | 48% | **6.4%** |

Retrieval effect (19 scored queries, `rag_eval`, live distractors present):

| | Old ingest | Re-ingest |
|---|---|---|
| P@1 (pool, no cut) | 15/19 | **16/19** |
| Recall@8, margin 0.20 | 19/19 | 19/19 |
| Recall@8, margin 0.08 | 17/19 | **19/19** |
| Worst rank | #8 (PPTX company facts) | **#1** |

The name-fragment pathology that caused the report's traced refusal chain is gone, and the
**margin brittleness has largely evaporated**: recall is 19/19 at every margin ≥ 0.08 because
content-free fragments no longer top-score at a large gap. `score_margin=0.20` remains the right
setting (avg 5.3 chunks kept ≈ ample evidence; 0.08 keeps only 1.9 and would re-starve
generation).

### 1.3 Summary routing — first measurement: **net regression as implemented**

`Retriever.retrieve()` restricts the chunk search to files whose summaries land in the top-k
summary hits (hard filter; plain search only as an empty-result fallback). A/B with the
production `Retriever`, routing on vs off:

| | Routed | Plain |
|---|---|---|
| P@1 | 15/19 | **16/19** |
| Recall | 18/19 | **19/19** |

- **Win:** it removes distractor files (`Sample - Superstore.csv`) from candidate sets in 3
  queries and lifted one tag-scoped rank #3 → #2.
- **Loss:** "When was DFFRNT founded…" — plain chunk search ranks the correct PPTX **#1**, but
  its summary missed the top-8 summary hits, so the hard filter made the correct document
  *unfindable*. A routing miss becomes an unrecoverable retrieval failure.

**Conclusion:** keep the summary signal, drop the hard filter (see change R1).

### 1.4 End-to-end answer quality (full pipeline, temp 0.1, 20 scored + 4 negatives)

| Metric | 2026-07-05 baseline (margin 0.08) | 2026-07-05 tuned (0.20) | **Today (0.20 + floor-128 re-ingest)** |
|---|---|---|---|
| Correctness | 11/19 (58%) | 14/19 (74%) | **16/19 (84%)** |
| Citation | 11/18 (61%) | 15/18 (83%) | **18/18 (100%)** |
| Refusal (4 negatives) | 4/4 | 4/4 | **4/4 (100%)** |
| Composite quality | 15/23 (65%) | 18/23 (78%) | **20/23 (87%)** |
| Latency mean / median / max | 34.5s / 29.5s / 73s | 40.5s / 35.2s / 84.8s | **37.3s / 31.5s / 87.4s** |

Per task: resume-HR **8/9** · proposal-correspondence **2/4** · knowledge-base **6/6**.
(answer_eval builds its pipeline without the summary store, so these numbers measure the
chunking + margin improvements; the routing layer is measured separately in §1.3.)

**The July failure mode is extinct.** Every answer carried citations (18/18) and no answerable
question was refused — the fast/uncited-refusal chain the July report traced (fragment at rank
1 → margin prunes the evidence → guardrail refuses) no longer occurs. The previously-failing
multi-document roll-ups (Figma aggregation, rate roll-up across 6 documents) now **pass**.

The 3 remaining failures are all *answered, cited, but missing one required fact group* —
completeness, not grounding:

- **Proposal fact lookup** (also the proposal-summary case): asked for the Aurora proposal's
  budget/timeline, the model answered "**approved at $258,000 for a 12-week timeline**" — the
  figures from the *correspondence that superseded the proposal*, not the proposal's original
  $240k/16-week (live probe verified; sources were the proposal at 0.74 plus four
  correspondence chunks). The system is doing temporal reconciliation across documents — for an
  executive audience this is arguably the *more* useful answer, but it should state both the
  original and the revision explicitly. This is a prompt-shaping issue (see P3.4), and partly a
  grading artifact of substring `must_include`.
- **Single-resume experience extraction** (Amara Okafor): answered with citations but one
  employer fact group missing — a completeness miss on a 4-chunk resume, the class that P1
  (summary in prompt) and R3 (context prefixes) target.

### 1.5 Harness/production divergence

`eval/answer_eval.py` and `eval/rag_eval.py` construct retrieval **without** `summary_store`
(`Retriever(store, llm, settings)`), so neither harness exercises the code path production runs
since PR #7. The routing A/B above required a custom script. This gap must close before routing
changes can be gated (change E1).

---

## 2. Assessment of the three proposed ideas

### Idea 1 — LLM summary in document metadata

**Already half-built.** Ingestion generates a 2–4 sentence LLM summary per document
(`ingest/summary.py`, ~18–30s per doc measured) and stores it in a dedicated collection
(`dffrnt_document_summaries`, 14 points after re-ingest; quality is high — spot-checked
summaries name entities, figures, and likely questions). But today the summary is **only** used
as a routing pre-filter — the text never reaches the model's prompt, so the intended benefit
("better model context impressions") is not yet realized. The user-entered `description` is
likewise stored on every chunk but never shown to the model.

What's missing (→ changes R1, P1, P2):
- Surface summaries in the generation prompt.
- Make routing a soft signal (measured regression as a hard filter).
- Backfill: documents ingested before PR #7 have no summary until re-uploaded (the two
  non-corpus documents in the live KB have none now).
- Make "summarize document X" queries hit the summary directly as a retrievable overview chunk.

### Idea 2 — system-prompt laxness with citation discipline

The current prompt is maximally defensive: binary answer-or-refuse ("If the documents do not
contain enough information, reply exactly …") plus per-sentence citation. The report's traced
failure mode (fast, uncited refusals on answerable questions) shows the model takes the refusal
exit whenever evidence looks thin, and the per-sentence mandate gives no rule for **tables**,
so tabular summaries force the model to either violate the mandate or bail — matching the
observed "doubts itself when summarizing in a circular fashion, especially during
tabularization."

The safety picture supports loosening: refusal accuracy has been 100% in *every* measured pass
(including stale-memory and tag-isolation probes) — the anti-fabrication margin is wide.
Retrieval starvation, the other historical cause of refusals, is now fixed. → change P3, gated
by the four negative controls + isolation probe staying at 100%.

### Idea 3 — RFP / team-resume generation readiness

Feasibility is good — the raw material is in place (per-resume summaries; floor-128 resumes are
compact: a full resume ≈ 700 chars ≈ 3–4 chunks, so **all five eval resumes together ≈ 3.5k
chars ≈ 900 tokens**, trivially inside `num_ctx=8192`). The blockers are architectural:

1. **Global top-k cannot guarantee per-person coverage.** "Rates of all candidates" needs one
   chunk from each of N documents; similarity search optimizes globally. Today's eval roll-ups
   pass with 5 resumes + roster (small corpus, dense chunks), but nothing *guarantees* coverage
   as the resume pool grows — at 30 resumes, top_k=8 provably cannot cover everyone.
   → grouped retrieval (R2).
2. **The 2000-char question cap** (`services.py`) forbids pasting an RFP template or an
   existing document to amend. → separate attachment field, not a cap raise (P4).
3. **Context budget**: template (~2–6k chars) + resumes + history approaches 8192; needs a
   measured `num_ctx` bump for this mode only, or 16384 globally if VRAM allows (KV-cache cost
   on the RTX 5070 Ti must be checked with `ollama ps`). → R4.
4. **Tag hygiene matters more**: RFP mode will scope by the `Resume` tag; the live KB has
   `Sample - Superstore.csv` tagged `Resume`, which would pollute any tag-scoped aggregation.
   Operational, not code — but worth a UI nudge or a warning when a tag spans wildly different
   file types.

---

## 3. Planned changes

Ordered by leverage per unit risk. Every retrieval-layer change is gated by `eval/rag_eval.py`
(+ routing mode, E1) and every prompt/generation change by `eval/answer_eval.py` with the
negative controls as a hard floor (refusal must stay 4/4).

### R — Retrieval & context assembly

- **R1 — Summary routing: hard filter → union (fixes measured regression).** ✅ **Done 2026-07-14.**
  `Retriever.retrieve()` now always runs the plain chunk search and merges in (dedup by
  chunk_id, score-ordered) any chunks from summary-matched files that plain search missed;
  summaries can no longer exclude a file. Unit-tested (`tests/unit/test_retriever.py`).
  A/B re-run: routed now equals plain on every rank metric (P@1 16/19, recall 19/19 — the §1.3
  MISS is gone) and adds evidence from summary-matched files (avg kept 5.3 → 5.8; the rate
  roll-up query gained two extra resume chunks). Requires an API image rebuild to reach
  production (code is baked into `dffrnt-assistant:latest`, not bind-mounted).
- **R2 — Grouped retrieval for aggregate queries (RFP prerequisite).** 🛠 **Implemented
  2026-07-14, not yet evaluated.** On aggregate intent (plural/roll-up cue regex, or any
  tag-scoped query), `Retriever.retrieve()` additionally runs Qdrant `query_points_groups`
  grouped by `filename` (`aggregate_group_limit=24` docs × `aggregate_group_size=1` chunks,
  both in config; 0 disables) and merges the results into the pool with the same additive
  union used for summary routing — a false-positive cue only adds chunks the margin cut can
  trim, never removes any. Smoke-tested live: a Resume-scoped rate query returns one best
  chunk from each of the 8 scoped documents. Unit-tested. Still to do: aggregate eval cases
  in `sample_queries.py` (E2) and a gating run.
- **R3 — Embed chunks with a context prefix.** ✅ **Done 2026-07-14 (gated).**
  `ingest/pipeline.py` now embeds each chunk as `filename · document_title · section_heading`
  + newline + chunk text (placeholder headings like `section3` filtered; parts de-duplicated);
  the stored payload text stays raw, so prompts are unchanged. Summary vectors likewise embed
  `filename · title · user description` + summary. Corpus re-ingested **in-process** (the API
  container's baked image predates this code — upload-path re-ingest would NOT have applied
  the prefixes). Gate (`rag_eval` before/after): P@1 16/19 and recall 19/19 held; correct-hit
  median rose 0.509 → **0.585**, and recall is now 19/19 at **every** margin ≥ 0.05 (before:
  a doc was lost at 0.05) — the margin knob is robust across its range now. Production A/B
  section: routed ≡ plain on all ranks, no REGRESSION lines. Note: any future ingestion-code
  change needs the same in-process re-ingest or an image rebuild first.
- **R4 — Context budget check for RFP mode.** ✅ **Measured 2026-07-14.**
  RTX 5070 Ti (16 GB): the 30B MoE **already spills to CPU at the current 8192** (19 GB
  footprint, 29%/71% CPU/GPU, 14.8 GB VRAM used). Raising context trades decode speed:

  | num_ctx | footprint | CPU/GPU | decode |
  |---|---|---|---|
  | 8192 (live) | 19 GB | 29% / 71% | 44.7 tok/s |
  | 12288 | 20 GB | 30% / 70% | 42.2 tok/s (−6%) |
  | 16384 | 20 GB | 32% / 68% | 39.2 tok/s (−12%) |

  **Recommendation:** keep `num_ctx = 8192` globally. For the P4 attachment flow either
  (a) cap attachments at ~12–16k chars (≈3–4k tokens; the prompt floor is ~0.9k tokens and
  aggregate queries now carry ~15–17 chunks ≈ 1.2k tokens), or (b) send `num_ctx = 16384`
  per-request for attachment-carrying queries only, accepting −12% decode plus a ~6.5s model
  reload whenever the context size switches (frequent switching thrashes the load). (a) is
  the simpler default; revisit (b) only if real RFP templates exceed the cap.

### P — Prompting & generation

- **P1 — Put document summaries in the prompt.** 🛠 **Implemented 2026-07-14, not yet
  evaluated.** `Retriever.retrieve()` stamps each surviving hit with its document's summary
  (from the summary hits already fetched, plus a by-filename fetch for any retrieved document
  whose summary missed the summary top-k — `VectorStore.payloads_by_filenames`).
  `build_context()` emits `<summary>…</summary>` inside the *first* `<document>` block of each
  distinct file, so the model gets one briefing per source. Cost ≈ 3–5 files × ~350 chars ≈
  400 tokens against the ~900-token prompt floor. No-op when a document has no summary (e.g.
  pre-backfill uploads) or when running without the summary store. Unit-tested.
- **P2 — Serve "summarize X" from the summary store.**
  When summary hits score far above chunk hits (or the query names a document), include the
  summary itself as a citable `<document>` entry. Alternative implementation: upsert summary
  points into the main collection as overview chunks (`summary_kind` already exists to
  distinguish them) — simpler retrieval, needs source-card dedup in the UI.
- **P3 — System-prompt v2 (idea 2), surgical additions, nothing removed.** ✅ **Done 2026-07-14.**
  Applied to `config.toml` (active) and `rag/prompt.py` (fallback, kept in sync). Gate re-run
  (full answer_eval, same settings): correctness 16→**17/19 (89%)** — the supersession rule
  recovered the proposal fact lookup; citation **18/18** held; refusal **4/4** and tag-isolation
  held (no fabrication regression from the loosening); composite quality 87%→**91%**; latency
  mean 37.3→40.4s (answers now state supersessions explicitly; within noise). Remaining 2
  failures are the completeness pair (single-resume extraction, proposal summary) targeted by
  P1/R3. Reaches production on API container restart (config.toml is bind-mounted). The rules:
  1. *Partial answers:* "If the documents contain part of the requested information, answer
     with what is supported and state explicitly what is missing. Use the refusal sentence only
     when no document contains relevant information."
  2. *Licensed synthesis:* "Reorganizing, comparing, tabulating, or summarizing information
     that appears in the documents is answering from the documents — derived statements must
     cite the sources they draw on."
  3. *Table citation rule:* "In tables, place the citation in the relevant cell or at the end
     of each row; a caption citation covering the whole table is acceptable when every value
     comes from the same source."
  4. *Supersession rule (from the §1.4 probe):* "When documents update or contradict each
     other (e.g. correspondence revising a proposal), give the latest agreed state AND note
     the original it replaced, citing both."
  Still open from this item: add 1–2 tabularization cases to `sample_queries.py` (e.g. "Table
  of all candidates with role and hourly rate") so the synthesis/table rules are directly
  measured rather than inferred (folded into E2).
- **P4 — Attachment field for RFP amendment (idea 3).**
  Add an optional `attachment` (or `reference_document`) field to `QueryRequest`, size-capped
  (~24k chars) and injected as a distinct `<reference_document>` block — do **not** raise the
  2000-char question cap (it exists to keep embeddings meaningful; the attachment must not be
  embedded, only the question is). The RFP prompt then becomes: question + reference template +
  grouped resume retrieval (R2).

### E — Evaluation & operations

- **E1 — Close the harness/production divergence.** ✅ **Done 2026-07-14 (code; first gated
  run pending).** `answer_eval` now builds retrieval exactly as `api/app.py` does — summary
  store included — by default (`--no-routing` isolates plain search), and `rag_eval` ends with
  a permanent production-vs-plain A/B section (`routing_ab`) that flags any query where the
  additive signals rank or recall worse than plain search as a REGRESSION. Note this shifts
  answer_eval's measured path: the next run is the first end-to-end number that includes
  routing + P1 summaries + R2 grouping.
- **E2 — Add RFP-shaped eval cases**: team-resume aggregation (must mention every scoped
  candidate), tabularization, amendment-with-attachment smoke test once P4 exists.
- **E3 — Summary backfill + bulk-ingest entry point.** ✅ **Done 2026-07-14.**
  New maintenance CLI `python -m dffrnt_assistant.ingest.backfill` (unit-tested, `--dry-run`
  supported): (1) default action generates summaries for any ingested document missing one —
  document text from the `data_dir` source file, else reconstructed from stored chunk
  payloads; tags/description/content_hash carried over from the chunks so tag-filtered
  summary search stays consistent. Run live: both non-corpus documents
  (`Sample - Superstore.csv`, `Resume-Sample-1-Software-Engineer.pdf`) now have summaries —
  16/16 documents covered. (2) `--ingest-missing` (opt-in) ingests supported `data_dir` files
  absent from the collection — the wiped-KB restore path; deliberately opt-in because the
  repo-root `data/` still holds two stale PDFs (`challengefund3…`, `dmava_mckinseyco.pdf`)
  from the pre-wipe corpus that would otherwise silently re-enter the KB (dry-run verified;
  not executed — owner's call).
- **E4 — Data hygiene**: correct `Sample - Superstore.csv` tags (currently `Resume`), and keep
  `eval/rag_eval.py` as the regression gate after any re-ingest (margin/top_k re-check).

### Deferred (unchanged from the July 5 report, still valid at larger corpus scale)

Hybrid dense+sparse retrieval (bge-m3 emits sparse weights natively); cross-encoder reranking;
structured SQLite route for CSV/XLSX aggregation (the §4.4 known-limit probe still applies —
numeric roll-ups over tables remain unguaranteed); CI wiring for nightly answer_eval.

---

## 4. Expected impact

| Use case | Today (measured) | After plan |
|---|---|---|
| Single-document Q&A | 84% correctness, 100% citation | Completeness gains (P1 summaries in prompt, R3 prefixes) |
| Summarize-a-document | Good; misses when summary chunk loses to detail chunks | Direct summary serving (P2) |
| Cross-document roll-ups | Pass at current corpus size; coverage not guaranteed at scale | Grouped retrieval (R2) makes coverage structural |
| Conflicting/updated documents | Reconciles silently to latest state | P3.4 makes the supersession explicit, cites both |
| Tabular briefings | Self-doubt / refusal risk (idea 2's complaint) | P3 licenses synthesis with a concrete table-citation rule |
| RFP / team resume | Blocked (2k question cap, no per-person coverage) | Unblocked by P4 + R2, context-budget verified by R4 |
| Anti-fabrication | 100% refusal, every pass since June | Preserved as a hard eval gate, not an assumption |

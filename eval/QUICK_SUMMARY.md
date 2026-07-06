# DFFRNT RAG Assistant — Quick Quantitative Summary

Companion to the full report: `eval/EVALUATION_REPORT.md`. Corpus: 14 synthetic
documents / 75 chunks, all 7 supported formats, controlled ground truth.

---

## 1. Model & system parameters

| Layer | Parameter | Value |
|---|---|---|
| LLM | Model | `qwen3:30b-a3b` (MoE) |
| LLM | Temperature | 0.1 |
| LLM | top_p / top_k | 0.95 / 20 |
| LLM | repeat_penalty | 1.0 |
| LLM | num_predict | -1 (uncapped) |
| LLM | num_ctx | 8192 |
| Embedding | Model | `bge-m3` |
| Embedding | Vector size | 1024 |
| Embedding | Query/doc prefix | none (blank — correct for bge-m3) |
| Vector store | Distance | cosine |
| Vector store | Index | brute-force (75 pts < 10k HNSW threshold) |
| Retrieval | top_k | 8 |
| Retrieval | score_margin | **0.08 → 0.20 (changed)** |
| Chunking | Strategy / size / overlap | recursive / 512 chars / 64 |
| Prompting | History turns | 6 |

---

## 2. Testing process & results, per metric

### Retrieval — P@1 (precision at rank 1)
**Test:** For each of 19 queries, embed the query, fetch top-8 candidates, check if the #1-ranked chunk belongs to the expected document.
**Result:** **15/19 (79%)** — unchanged by the margin tune (P@1 depends only on ranking, not the cut).

### Retrieval — Recall@8
**Test:** After applying `top_k=8` + `score_margin`, check if *any* expected document survived.
**Result:** **17/19 (89%) → 19/19 (100%)** after `score_margin` 0.08 → 0.20.

### Retrieval — correct-hit score band
**Test:** Record the cosine similarity of every hit that was actually correct, across all queries.
**Result:** **min 0.334 · median 0.493 · max 0.832** — wider than the band the old margin (0.08) was tuned against; explains why it over-pruned.

### Generation — Correctness
**Test:** Full RAG pipeline answers each query; check the answer contains every required fact (`must_include` groups, read directly off the corpus).
**Result:** **11/19 (58%) → 14/19 (74%)** after the margin tune.

### Generation — Citation coverage
**Test:** Check each answer for at least one inline `[n]` marker, per the system prompt's citation mandate.
**Result:** **11/18 (61%) → 15/18 (83%)**.

### Generation — Refusal accuracy (anti-hallucination)
**Test:** 4 out-of-corpus negative controls + 1 tag-isolation probe; check the answer is the exact canonical refusal sentence (no fabrication).
**Result:** **4/4 (100%)**, unchanged across both passes — refusal behavior held steady while the margin loosened.

### Generation — Composite quality
**Test:** `(correct + refused) / (scored + negatives)` — single number rewarding both correct answers and correct refusals.
**Result:** **15/23 (65%) → 18/23 (78%)**.

### Generation — Latency
**Test:** Wall-clock seconds per query, full pipeline, 24 queries per pass.
**Result:** mean **34.5s → 40.5s**, median **29.5s → 35.2s**, max **73.0s → 84.8s** (+17% mean latency for +16pp correctness).

### Ingestion — Chunk size distribution
**Test:** Measure character length of every stored chunk against the configured `chunk_size=512`.
**Result:** median **108 chars** (21% of target); **48% of chunks under 100 chars**.

### Software — Unit tests
**Test:** `pytest tests/` — chunker, loaders, config, tags, schema, Ollama client.
**Result:** **26 passed, 4 deselected.**

---

## 3. Diagnosis

**Root cause #1 — `score_margin` was corpus-mistuned.** It was set to 0.08 on a
prior corpus with a narrower cosine score spread. On this corpus (spread
0.33–0.83), that fixed relative cut pruned correct documents below the top hit,
directly causing retrieval recall loss and, downstream, fast/uncited refusals
on answerable questions. **Fix applied:** `score_margin` → 0.20 (config.toml),
API restarted and verified live. Recovered 3 correctness cases and 4 citation
cases at the cost of ~17% more latency.

**Root cause #2 — chunk fragmentation at ingestion (unresolved).** Loaders
emit one section per paragraph/heading/slide; the chunker never packs across
section boundaries, so 48% of chunks are under 100 characters — some holding
only a name or heading with no answerable content. This is what put a
content-free fragment at rank 1 in the traced failure case (Amara Okafor's
resume, correct document, but the surviving chunk was the 12-character name
fragment). **All 5 remaining post-tune failures trace to this same mechanism**
— no margin value fixes it; it requires packing chunks across sections at
ingest time.

**What is *not* broken:** the embedding model, the LLM, and the
anti-hallucination guardrail. Refusal accuracy held at 100% through both
passes, including a stale-memory probe and a tag-isolation probe — the model
never fabricated an answer it didn't have grounds for.

**Next highest-leverage fix:** pack loader sections before chunking (or merge
sub-`chunk_size` sections) and drop near-empty (<30 char) chunks. This directly
targets the still-unresolved 26% correctness gap.

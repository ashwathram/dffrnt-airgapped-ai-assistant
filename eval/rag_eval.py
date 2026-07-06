"""Retrieval hyperparameter sweep for the DFFRNT RAG agent.

Embeds each sample query once against the live Ollama + Qdrant stack, fetches a
generous candidate pool, then *simulates* every (top_k, score_margin) config
offline — top_k is a slice and score_margin is a relative cut from the best hit,
so no re-embedding is needed per config. Reports P@1 (rank-1 correct), recall
(any expected doc kept after the margin cut), and the average number of chunks
that survive the cut (prompt size proxy).

Run from the repo root:  python -m eval.rag_eval
Requires the same services the app uses (Ollama + Qdrant) to be up.
"""

from __future__ import annotations

import statistics
from typing import Dict, List

from dffrnt_assistant.config import load_settings
from dffrnt_assistant.ollama import OllamaClient
from dffrnt_assistant.retrieval.store import VectorStore

from eval.sample_queries import CASES, TAG_CASES

CANDIDATE_POOL = 15                      # fetch this many, then simulate smaller top_k
TOP_K_GRID = [5, 8, 10, 12]
MARGIN_GRID = [0.0, 0.05, 0.08, 0.10, 0.12, 0.15, 0.20]


def fetch_candidates(store, embedder, settings) -> List[Dict]:
    """For each case, the ranked (filename, score) list from one live search.

    Tag-scoped cases run with their tag filter, exactly as the UI would send
    them; the isolation probe (empty ``expected``) is excluded — retrieval rank
    metrics are undefined when no document is supposed to match."""
    rows = []
    for case in list(CASES) + [c for c in TAG_CASES if c["expected"]]:
        vec = embedder.embed_query(case["query"])
        hits = store.search(vec, CANDIDATE_POOL, case.get("tags"))
        ranked = [(h["payload"].get("filename"), h["score"]) for h in hits]
        rows.append({**case, "ranked": ranked})
    return rows


def apply_config(ranked: List, top_k: int, margin: float) -> List:
    """Reproduce Retriever.retrieve: take top_k, then drop hits more than
    `margin` below the best score (top hit always kept; margin 0 disables)."""
    kept = ranked[:top_k]
    if kept and margin > 0:
        cutoff = kept[0][1] - margin
        kept = [r for r in kept if r[1] >= cutoff]
    return kept


def score_config(rows: List[Dict], top_k: int, margin: float) -> Dict:
    p1 = recall = 0
    kept_counts = []
    for row in rows:
        kept = apply_config(row["ranked"], top_k, margin)
        kept_counts.append(len(kept))
        files = [f for f, _ in kept]
        if files and files[0] in row["expected"]:
            p1 += 1
        if any(f in row["expected"] for f in files):
            recall += 1
    n = len(rows)
    return {
        "top_k": top_k,
        "margin": margin,
        "p_at_1": p1,
        "recall": recall,
        "n": n,
        "avg_kept": statistics.mean(kept_counts) if kept_counts else 0,
    }


def main() -> None:
    settings = load_settings()
    store = VectorStore(
        settings.qdrant_url, settings.collection_name, settings.vector_size, settings.distance
    )
    embedder = OllamaClient(
        settings.ollama_url, settings.llm_model, settings.embed_model,
        settings.llm_temperature, settings.llm_timeout,
        settings.embed_query_prefix, settings.embed_document_prefix,
    )

    print(f"Embed model: {settings.embed_model}  distance: {settings.distance}")
    print(f"Live config: top_k={settings.top_k}  score_margin={settings.score_margin}\n")

    rows = fetch_candidates(store, embedder, settings)

    # Per-query diagnostic: where does the first correct doc land, and the band.
    print("=== Per-query (rank of first correct doc | best score | that score) ===")
    for row in rows:
        files = [f for f, _ in row["ranked"]]
        rank = next((i + 1 for i, f in enumerate(files) if f in row["expected"]), None)
        best = row["ranked"][0][1] if row["ranked"] else float("nan")
        correct_score = next((s for f, s in row["ranked"] if f in row["expected"]), None)
        rank_str = f"#{rank}" if rank else "MISS"
        cs = f"{correct_score:.3f}" if correct_score is not None else "  -  "
        print(f"  [{rank_str:>4}] best={best:.3f} correct={cs}  {row['note']}")

    # Score band across all correct hits — informs the score_margin scale.
    correct_scores = [
        s for row in rows for f, s in row["ranked"] if f in row["expected"]
    ]
    if correct_scores:
        print(
            f"\nCorrect-hit score band: min={min(correct_scores):.3f} "
            f"median={statistics.median(correct_scores):.3f} max={max(correct_scores):.3f}"
        )

    print("\n=== Config sweep (P@1 / recall out of N, avg kept chunks) ===")
    print(f"{'top_k':>6} {'margin':>7} {'P@1':>8} {'recall':>8} {'avg_kept':>9}")
    results = []
    for top_k in TOP_K_GRID:
        for margin in MARGIN_GRID:
            r = score_config(rows, top_k, margin)
            results.append(r)
            print(
                f"{r['top_k']:>6} {r['margin']:>7.2f} "
                f"{r['p_at_1']:>4}/{r['n']:<3} {r['recall']:>4}/{r['n']:<3} {r['avg_kept']:>9.1f}"
            )

    # Best = maximise recall, then P@1, then fewest kept chunks (tighter prompt).
    best = max(results, key=lambda r: (r["recall"], r["p_at_1"], -r["avg_kept"]))
    print(
        f"\nBest by (recall, P@1, tightness): top_k={best['top_k']} "
        f"score_margin={best['margin']:.2f}  "
        f"-> P@1 {best['p_at_1']}/{best['n']}, recall {best['recall']}/{best['n']}, "
        f"avg_kept {best['avg_kept']:.1f}"
    )


if __name__ == "__main__":
    main()

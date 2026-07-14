"""Compare chunking configurations on the same corpus.

This is a lightweight before/after harness for chunk optimization work.
It does not touch Qdrant or the live app. Instead, it loads each corpus
document, runs the configured chunker, and reports how the chunk shape changes.

Use it to validate changes like:
  - chunk floor / tiny-chunk suppression
  - chunk concatenation / packing
  - recursive chunking

Examples:
  python -m eval.chunk_health --corpus eval/corpus
  python -m eval.chunk_health --corpus eval/corpus --candidate-strategy recursive --candidate-size 768 --candidate-overlap 96
  python -m eval.chunk_health --corpus eval/corpus --baseline-strategy fixed --baseline-size 512 --baseline-overlap 64 --candidate-strategy recursive --candidate-size 768 --candidate-overlap 96
"""

from __future__ import annotations

import argparse
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

from dffrnt_assistant.ingest.chunker import chunk_file
from dffrnt_assistant.ingest.loaders import load_file


@dataclass(frozen=True)
class ChunkStats:
    docs: int
    chunks: int
    avg_chunks_per_doc: float
    avg_chunk_chars: float
    median_chunk_chars: float
    p10_chunk_chars: float
    tiny_lt_30: float
    tiny_lt_100: float
    tiny_lt_200: float
    avg_doc_chars: float


def _percentile(values: Sequence[int], pct: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    ordered = sorted(values)
    idx = (len(ordered) - 1) * pct
    lo = int(idx)
    hi = min(lo + 1, len(ordered) - 1)
    frac = idx - lo
    return ordered[lo] * (1 - frac) + ordered[hi] * frac


def _fmt_pct(value: float) -> str:
    return f"{value:.1f}%"


def _load_documents(corpus_dir: Path) -> List[Path]:
    files = [p for p in corpus_dir.iterdir() if p.is_file()]
    return sorted(files, key=lambda p: p.name.lower())


def _loader_support_hint(path: Path) -> str | None:
    suffix = path.suffix.lower()
    if suffix == ".pptx":
        return "python-pptx"
    if suffix == ".xlsx":
        return "openpyxl"
    if suffix == ".docx":
        return "python-docx"
    if suffix == ".pdf":
        return "pymupdf"
    return None


def _chunk_lengths_for_doc(path: Path, strategy: str, chunk_size: int, overlap: int) -> List[int]:
    document = load_file(str(path))
    chunks = chunk_file(document, strategy=strategy, chunk_size=chunk_size, overlap=overlap)
    return [len((chunk.get("text") or "")) for chunk in chunks]


def summarize(
    corpus_dir: Path, strategy: str, chunk_size: int, overlap: int, chunk_floor: int
) -> Tuple[ChunkStats, Dict[str, List[int]], Dict[str, str]]:
    per_doc: Dict[str, List[int]] = {}
    doc_chars: List[int] = []
    skipped: Dict[str, str] = {}
    for path in _load_documents(corpus_dir):
        try:
            document = load_file(str(path))
            chunks = chunk_file(
                document,
                strategy=strategy,
                chunk_size=chunk_size,
                overlap=overlap,
                chunk_floor=chunk_floor,
            )
            lengths = [len((chunk.get("text") or "")) for chunk in chunks]
        except Exception as exc:  # optional parsers may be absent in minimal envs
            hint = _loader_support_hint(path)
            skipped[path.name] = f"{exc}" + (f" (install {hint})" if hint else "")
            continue
        per_doc[path.name] = lengths
        doc_chars.append(sum(lengths))

    all_lengths = [n for lengths in per_doc.values() for n in lengths]
    docs = len(per_doc)
    chunks = len(all_lengths)
    stats = ChunkStats(
        docs=docs,
        chunks=chunks,
        avg_chunks_per_doc=(chunks / docs) if docs else 0.0,
        avg_chunk_chars=statistics.mean(all_lengths) if all_lengths else 0.0,
        median_chunk_chars=statistics.median(all_lengths) if all_lengths else 0.0,
        p10_chunk_chars=_percentile(all_lengths, 0.10) if all_lengths else 0.0,
        tiny_lt_30=(100 * sum(1 for n in all_lengths if n < 30) / chunks) if chunks else 0.0,
        tiny_lt_100=(100 * sum(1 for n in all_lengths if n < 100) / chunks) if chunks else 0.0,
        tiny_lt_200=(100 * sum(1 for n in all_lengths if n < 200) / chunks) if chunks else 0.0,
        avg_doc_chars=statistics.mean(doc_chars) if doc_chars else 0.0,
    )
    return stats, per_doc, skipped


def print_stats(label: str, strategy: str, chunk_size: int, overlap: int, stats: ChunkStats) -> None:
    print(f"{label}: strategy={strategy} size={chunk_size} overlap={overlap}")
    print(f"  docs: {stats.docs}")
    print(f"  chunks: {stats.chunks}")
    print(f"  avg chunks/doc: {stats.avg_chunks_per_doc:.2f}")
    print(f"  avg chunk chars: {stats.avg_chunk_chars:.1f}")
    print(f"  median chunk chars: {stats.median_chunk_chars:.1f}")
    print(f"  p10 chunk chars: {stats.p10_chunk_chars:.1f}")
    print(f"  tiny chunks <30 chars: {_fmt_pct(stats.tiny_lt_30)}")
    print(f"  tiny chunks <100 chars: {_fmt_pct(stats.tiny_lt_100)}")
    print(f"  tiny chunks <200 chars: {_fmt_pct(stats.tiny_lt_200)}")
    print(f"  avg doc chars from chunks: {stats.avg_doc_chars:.1f}")


def print_diff(base: ChunkStats, cand: ChunkStats) -> None:
    print("Delta (candidate - baseline):")
    print(f"  chunks: {cand.chunks - base.chunks:+d}")
    print(f"  avg chunks/doc: {cand.avg_chunks_per_doc - base.avg_chunks_per_doc:+.2f}")
    print(f"  avg chunk chars: {cand.avg_chunk_chars - base.avg_chunk_chars:+.1f}")
    print(f"  median chunk chars: {cand.median_chunk_chars - base.median_chunk_chars:+.1f}")
    print(f"  p10 chunk chars: {cand.p10_chunk_chars - base.p10_chunk_chars:+.1f}")
    print(f"  tiny chunks <30 chars: {cand.tiny_lt_30 - base.tiny_lt_30:+.1f} pp")
    print(f"  tiny chunks <100 chars: {cand.tiny_lt_100 - base.tiny_lt_100:+.1f} pp")
    print(f"  tiny chunks <200 chars: {cand.tiny_lt_200 - base.tiny_lt_200:+.1f} pp")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus", type=Path, default=Path("eval/corpus"), help="corpus directory")
    ap.add_argument("--baseline-strategy", default="recursive")
    ap.add_argument("--baseline-size", type=int, default=512)
    ap.add_argument("--baseline-overlap", type=int, default=64)
    ap.add_argument("--baseline-floor", type=int, default=0)
    ap.add_argument("--candidate-strategy", default=None)
    ap.add_argument("--candidate-size", type=int, default=None)
    ap.add_argument("--candidate-overlap", type=int, default=None)
    ap.add_argument("--candidate-floor", type=int, default=None)
    args = ap.parse_args()

    corpus_dir = args.corpus
    if not corpus_dir.exists():
        raise SystemExit(f"Corpus directory not found: {corpus_dir}")

    cand_strategy = args.candidate_strategy or args.baseline_strategy
    cand_size = args.candidate_size if args.candidate_size is not None else args.baseline_size
    cand_overlap = args.candidate_overlap if args.candidate_overlap is not None else args.baseline_overlap
    cand_floor = args.candidate_floor if args.candidate_floor is not None else args.baseline_floor

    base_stats, base_per_doc, base_skipped = summarize(
        corpus_dir, args.baseline_strategy, args.baseline_size, args.baseline_overlap, args.baseline_floor
    )
    cand_stats, cand_per_doc, cand_skipped = summarize(
        corpus_dir, cand_strategy, cand_size, cand_overlap, cand_floor
    )

    print("=== Chunk Health Comparison ===\n")
    print_stats(
        "Baseline",
        args.baseline_strategy,
        args.baseline_size,
        args.baseline_overlap,
        base_stats,
    )
    print()
    print_stats("Candidate", cand_strategy, cand_size, cand_overlap, cand_stats)
    print()
    print_diff(base_stats, cand_stats)

    print("\nPer-document chunk counts (baseline -> candidate):")
    for name in sorted(base_per_doc):
        b = len(base_per_doc[name])
        c = len(cand_per_doc.get(name, []))
        print(f"  {name}: {b} -> {c}")

    skipped = sorted(set(base_skipped) | set(cand_skipped))
    if skipped:
        print("\nSkipped documents (missing parser support or load error):")
        for name in skipped:
            reason = base_skipped.get(name) or cand_skipped.get(name) or "unknown"
            print(f"  {name}: {reason}")


if __name__ == "__main__":
    main()

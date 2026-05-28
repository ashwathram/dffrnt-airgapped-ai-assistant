# Semantic Search Demo Guide

This document explains what `scripts/semantic_search_demo.py` does and how to revise it.

## Purpose

`semantic_search_demo.py` is a local retrieval test harness. It:

1. loads one or more source documents,
2. chunks the text using a selected chunking method,
3. embeds each chunk,
4. stores the chunk vectors in Qdrant,
5. generates labeled queries from the chunks when running in evaluation mode, and
6. reports retrieval accuracy.

The goal is to compare retrieval quality, especially across different chunking methods, before any answer generation happens.

## Current Behavior

### Default mode

If you run the script without `--query`, it enters evaluation mode.

In evaluation mode it:

- scans `database/raw` recursively by default,
- can be limited with `--source` and `--limit-files`,
- evaluates each supported file it finds,
- runs the selected chunking methods:
  - `fixed`
  - `sentence`
  - `paragraph`
  - `recursive`
- generates 20 labeled test queries per document by default,
- compares the retrieved chunks against the expected chunk IDs,
- prints per-file accuracy and an aggregate summary.

### Manual query mode

If you pass one or more `--query` values, the script switches to manual query mode.

In that mode it:

- selects the first available document from the provided scope,
- ingests that document,
- runs your custom queries,
- prints the top-k retrieval results,
- does not calculate accuracy automatically.

## Important CLI Options

- `document`
  - Optional single file path.
  - If provided, the script can use that file directly.

- `--source`
  - Repeatable file or folder input.
  - Use this to limit evaluation to a folder like `database/raw/Client_Related` or to a specific file.

- `--limit-files`
  - Caps how many files are evaluated after source expansion.

- `--chunking-methods`
  - Comma-separated list of chunking strategies to compare.
  - Supported values: `fixed`, `sentence`, `paragraph`, `recursive`.

- `--chunk-size`
  - Maximum chunk size in characters.

- `--overlap`
  - Overlap used by fixed and recursive chunking.

- `--eval-count`
  - Number of labeled queries to generate per document in evaluation mode.
  - Default: 20.

- `--top-k`
  - Number of retrieved results to print for each query.

- `--query`
  - Manual query mode input.
  - If present, the script does not run the automatic accuracy evaluation.

## What It Measures

The script measures retrieval accuracy, not answer-generation accuracy.

A query is counted as correct when the expected chunk ID appears in the retrieved top-k results.

Accuracy is calculated as:

$$
\text{accuracy} = \frac{\text{correct queries}}{\text{total queries}}
$$

If the result is $0.85$ or higher, the retriever meets the 85% target for that file and chunking method.

## Why Chunking Matters

Chunking is a major design decision because it affects:

- how much context each chunk contains,
- whether related facts stay together,
- how much noise is introduced into embeddings,
- whether the retriever can find the right chunk for a factual query.

The current script is designed to compare these methods:

- Fixed-size chunking
- Sentence chunking
- Paragraph chunking
- Recursive chunking

## How to Revise the Demo

If you want to change the script, these are the main places to look:

- `src/processing/chunker.py`
  - add or modify chunking strategies here.

- `scripts/semantic_search_demo.py`
  - change file selection, query generation, evaluation rules, or reporting here.

- `src/embeddings/embedder.py`
  - change the embedding model or fallback behavior here.

- `src/vector_store/qdrant_store.py`
  - adjust Qdrant storage or search behavior here.

## Typical Revision Goals

You may want to revise the demo to:

- test only one folder, such as `database/raw/Client_Related`,
- compare chunking methods on the same documents,
- change the number of generated test queries,
- change how a query is judged correct,
- print more detailed scoring output,
- store evaluation results in a file.

## Example Commands

Run evaluation mode on the default dataset:

```powershell
python scripts/semantic_search_demo.py
```

Limit evaluation to one folder:

```powershell
python scripts/semantic_search_demo.py --source "database/raw/Client_Related"
```

Limit to one file:

```powershell
python scripts/semantic_search_demo.py --source "database/raw/Client_Related/Sample - Superstore.csv"
```

Manual query mode:

```powershell
python scripts/semantic_search_demo.py --source "database/raw/Client_Related" --query "revenue summary" --query "banana recipe"
```

## Suggested Next Improvement

Add a small saved-results report, such as CSV or JSON, so the demo can track chunking-method accuracy over time.

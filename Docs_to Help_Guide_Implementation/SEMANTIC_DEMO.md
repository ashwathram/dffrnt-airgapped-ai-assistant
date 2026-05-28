# Semantic Search Demo

File: Docs_to Help_Guide_Implementation/SEMANTIC_DEMO.md

Purpose
- Explain `scripts/semantic_search_demo.py`, its inputs, behavior, and related modules.

Overview
- The demo ingests a single document, chunks the text, computes embeddings for chunks, upserts vectors to a Qdrant collection, and runs queries to print the top-k results.

How the script chooses the document
- If you pass a `document` path on the command line, the script uses that file in single-document query mode.
- If you omit `document`, the script scans `database/raw` recursively and evaluates every supported file it finds.
- You can limit the evaluation scope with `--source` (repeatable file or folder paths) and `--limit-files`.
- Supported extensions are `.pdf`, `.docx`, `.pptx`, `.csv`, `.txt`, `.md`.

Key functions (quick reference)
- `build_demo_collection_name(document_path: Path) -> str`: create a safe Qdrant collection name from the filename.
- `ingest_document(document_path: Path, collection_name: str, embedder, chunking_method, chunk_size, overlap) -> (store, embedder, chunks)`: loads the document, chunks it using the selected strategy, encodes the chunks, and upserts to Qdrant.
- `print_results(store, embedder, query, top_k)`: embeds the query and prints the top-k matches with score and excerpt.
- `build_eval_queries(chunks, eval_count)`: turns chunks into labeled evaluation queries.
- `collect_documents(source_paths, limit_files)`: expands file/folder inputs into a unique list of supported documents.
- `evaluate_document(...)`: runs one document through one chunking strategy and returns correct/total/accuracy.

Related modules
- `src/embeddings/embedder.py`: uses `sentence-transformers` if installed; otherwise a deterministic fallback. Install `sentence-transformers` + `torch` for real semantic embeddings.
- `src/ingestion/loaders.py`: document parsing and metadata extraction.
- `src/processing/chunker.py`: fixed-size, sentence, paragraph, and recursive chunking methods.
- `src/vector_store/qdrant_store.py`: wrapper around `qdrant-client` for collection management, upsert, and search. Requires Qdrant running at `http://localhost:6333` by default.

Dependencies
- Python 3.14 recommended (project venv for this repo uses 3.14).
- Key Python packages installed in the project venv: `numpy`, `pandas`, `qdrant-client`, `PyPDF2`, `pytest`, `sentence-transformers`, `torch` (if using real embeddings).
- Qdrant (recommended via Docker):
```powershell
docker run -d --name qdrant -p 6333:6333 -v qdrant_data:/qdrant/storage qdrant/qdrant
```

Usage
1) Activate the project virtual environment (PowerShell):
```powershell
& ".\.venv\Scripts\Activate.ps1"
```
2) Run the demo with an explicit file:
```powershell
python scripts/semantic_search_demo.py "path\to\file.pdf"
```
Or evaluate everything in `database/raw` recursively:
```powershell
python scripts/semantic_search_demo.py
```
Or limit the scope to a folder or file:
```powershell
python scripts/semantic_search_demo.py --source "database/raw/Client_Related" --limit-files 5
```

Command-line options
- `document`: optional single file path for query mode.
- `--source <path>`: repeatable file or folder input for evaluation mode. Folders are scanned recursively.
- `--limit-files <n>`: cap the number of files evaluated after expansion.
- `--chunking-methods fixed,sentence,paragraph,recursive`: choose which chunking methods to compare.
- `--chunk-size <n>`: maximum chunk size in characters.
- `--overlap <n>`: overlap used by fixed and recursive chunking.
- `--top-k <n>`: number of results to show per query when printing each query's matches (default: 3).
- `--eval-count <n>`: number of labeled test queries generated per document in evaluation mode (default: 20).
- `--query <text>`: manual query mode. If provided, the script uses your queries and skips automatic accuracy scoring.

Examples
- Use a specific file and custom queries:
```powershell
python scripts/semantic_search_demo.py "database/raw/sample.pdf" --query "project overview" --query "installation steps"
```
- Compare all supported files in `database/raw` with the default chunking methods:
```powershell
python scripts/semantic_search_demo.py
```

What the semantic demo does now
- In evaluation mode, it loops through every supported file found under `database/raw` recursively unless you restrict it with `--source` or `--limit-files`.
- For each file, it runs the selected chunking methods and creates 20 labeled queries from the chunks by default.
- It scores retrieval as `correct / total` for each file and method, then prints an aggregate summary so you can compare chunking strategies.
- In manual query mode, it uses your explicit queries against the first selected file.

Expected output
- The script prints the number of chunks ingested and, for each query, the top-k results displaying `score`, `file`, and a short `excerpt` from the matched chunk.

Where to test retrieval accuracy
- Test accuracy at the retrieval step, after ingestion and before any final answer generation.
- In this demo, that means the check happens inside `print_results()` right after `store.search(query_vector, top=top_k)`.
- For an 85% target, use the generated labeled queries or your own labeled factual queries and verify whether the expected chunk appears in the retrieved results.
- The built-in eval mode now uses 20 labeled queries per document by default and prints `correct / total` for each chunking method.
- A simple pass rule is: count a query as correct when the expected chunk ID appears in the top-k retrieved results.
- Hitting 0.85 or higher means the retriever is meeting the target for that file and chunking method.
- This is the best place to test because it isolates retrieval quality from answer-generation quality.

Troubleshooting
- If unrelated queries return similar scores to related queries, ensure `sentence-transformers` and `torch` are installed in the venv so the `Embedder` uses a real model (not the fallback).
- If Qdrant operations fail, verify Qdrant is running and reachable at `http://localhost:6333` and that `qdrant-client` is installed in the venv.
- If no document is found, add a supported file to `database/raw` or run the script with an explicit `document` path.

Next steps
- Add a small CI smoke test that ingests a known sample file in `database/raw` and asserts that the related default query returns a top result above a configurable score threshold.


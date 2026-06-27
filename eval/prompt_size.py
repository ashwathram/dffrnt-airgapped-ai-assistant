"""Estimate real RAG prompt sizes to size the LLM context window (num_ctx).

For each sample query it builds the *actual* prompt the app would send (system
prompt + retrieved <documents> at the configured top_k + question) and reports
its size. We estimate tokens as chars/4 (a stable proxy) rather than calling the
LLM: qwen3's thinking mode ignores num_predict=0, so a true tokenize call costs
a full 30B generation per query. The point is only to show the prompt floor
relative to Ollama's 4096 default, which silently truncates anything larger.

Run from the repo root:  python -m eval.prompt_size
"""

from __future__ import annotations

from dffrnt_assistant.config import load_settings
from dffrnt_assistant.ollama import OllamaClient
from dffrnt_assistant.rag.prompt import DEFAULT_SYSTEM_PROMPT, build_prompt
from dffrnt_assistant.retrieval.retriever import Retriever
from dffrnt_assistant.retrieval.store import VectorStore

from eval.sample_queries import CASES


def main() -> None:
    s = load_settings()
    store = VectorStore(s.qdrant_url, s.collection_name, s.vector_size, s.distance)
    emb = OllamaClient(
        s.ollama_url, s.llm_model, s.embed_model, s.llm_temperature,
        s.llm_timeout, s.embed_query_prefix, s.embed_document_prefix,
    )
    r = Retriever(store, emb, s)
    sysp = s.system_prompt or DEFAULT_SYSTEM_PROMPT

    print(f"top_k={s.top_k}  score_margin={s.score_margin}  chunk_size={s.chunk_size} chars")
    print(f"{'chars':>7} {'~tok':>6} {'kept':>4}  query")
    mx = 0
    for c in CASES:
        hits = r.retrieve(c["query"])
        ctx = r.build_context(hits)
        prompt = build_prompt(sysp, ctx, "", c["query"])  # no history = floor
        ch = len(prompt)
        tok = ch // 4
        mx = max(mx, tok)
        print(f"{ch:>7} {tok:>6} {len(hits):>4}  {c['query'][:48]}")

    print(f"\nNo-history floor: max ~{mx} tokens (chars/4).")
    print("Ollama default num_ctx=4096. History (up to 6 turns) and pasted "
          "questions (up to 2000 chars ~ 500 tok) stack on top of this floor.")


if __name__ == "__main__":
    main()

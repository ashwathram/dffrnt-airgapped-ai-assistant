import sys
sys.path.append("..")
from config import OLLAMA_URL, LLM_MODEL, EMBED_MODEL
from langchain_ollama import OllamaLLM, OllamaEmbeddings

def get_llm():
    """Returns connection to the local language model."""
    return OllamaLLM(
        base_url=OLLAMA_URL,
        model=LLM_MODEL,
        temperature=0.1,
    )

def get_embedder():
    """Returns connection to the local embedding model."""
    return OllamaEmbeddings(
        base_url=OLLAMA_URL,
        model=EMBED_MODEL,
    )

if __name__ == "__main__":
    print(f"Testing LLM: {LLM_MODEL}")
    response = get_llm().invoke("What is 2+2? Answer in one word only.")
    print(f"LLM response: {response}")

    print(f"\nTesting embedder: {EMBED_MODEL}")
    vector = get_embedder().embed_query("test sentence")
    print(f"Embedding dimensions: {len(vector)}")

    if len(vector) == 768:
        print("\nM3 test PASSED ✓")
    else:
        print("\nM3 test FAILED ✗")

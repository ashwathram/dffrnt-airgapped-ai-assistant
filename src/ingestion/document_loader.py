import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import CHUNK_SIZE, CHUNK_OVERLAP
from pathlib import Path
from langchain_text_splitters import RecursiveCharacterTextSplitter

def load_file(file_path):
    """Loads a file and returns list of LangChain Document objects."""
    path = Path(file_path)
    ext  = path.suffix.lower()
    try:
        if ext == ".pdf":
            from langchain_community.document_loaders import PyMuPDFLoader
            return PyMuPDFLoader(file_path).load()
        elif ext == ".docx":
            from langchain_community.document_loaders import Docx2txtLoader
            return Docx2txtLoader(file_path).load()
        elif ext == ".pptx":
            from langchain_community.document_loaders import UnstructuredPowerPointLoader
            return UnstructuredPowerPointLoader(file_path).load()
        elif ext == ".txt":
            from langchain_community.document_loaders import TextLoader
            return TextLoader(file_path).load()
        elif ext == ".csv":
            from langchain_community.document_loaders import CSVLoader
            return CSVLoader(file_path).load()
        else:
            print(f"Skipping unsupported file type: {ext}")
            return []
    except Exception as e:
        print(f"Error loading {path.name}: {e}")
        return []

def split_into_chunks(documents, filename):
    """Splits documents into chunks with metadata."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    chunks = splitter.split_documents(documents)
    return [
        {
            "text": chunk.page_content,
            "metadata": {
                "filename":    filename,
                "page":        chunk.metadata.get("page", i),
                "chunk_index": i,
            }
        }
        for i, chunk in enumerate(chunks)
    ]

def ingest_file(file_path, qdrant_client, embedder):
    """Full pipeline: load → chunk → embed → store. Returns chunk count."""
    filename  = Path(file_path).name
    print(f"Ingesting: {filename}")

    documents = load_file(file_path)
    if not documents:
        print(f"  No content loaded from {filename}")
        return 0

    chunks = split_into_chunks(documents, filename)
    if not chunks:
        print(f"  No chunks created from {filename}")
        return 0

    print(f"  Embedding {len(chunks)} chunks...")
    embeddings = embedder.embed_documents([c["text"] for c in chunks])

    from vectorstore.vector_store import store_chunks
    store_chunks(qdrant_client, chunks, embeddings)
    print(f"  Done: {len(chunks)} chunks stored")
    return len(chunks)

def ingest_folder(folder_path, qdrant_client, embedder):
    """Ingests all supported files in a folder."""
    supported = {".pdf", ".docx", ".pptx", ".txt", ".csv"}
    total = 0
    for f in Path(folder_path).rglob("*"):
        if f.suffix.lower() in supported:
            total += ingest_file(str(f), qdrant_client, embedder)
    print(f"\nIngestion complete: {total} total chunks stored")
    return total

if __name__ == "__main__":
    from vectorstore.vector_store import get_client, create_collection
    from llm.llm_client import get_embedder

    print("Testing M1 Document Ingestion...")

    os.makedirs("data", exist_ok=True)
    with open("data/test_doc.txt", "w") as f:
        f.write("""DFFRNT Company Profile

DFFRNT is a management consulting firm specializing in digital transformation.
Founded in 2018, the company works with businesses to improve operational efficiency.

Services include:
- Data strategy consulting
- RFP response preparation
- AI knowledge management
- Digital transformation roadmaps

Key personnel:
Sarah Johnson has 10 years experience in financial services and has led 15 RFPs.
John Smith specializes in healthcare data analytics with 8 years experience.
The team has completed 45 projects across healthcare, finance, and retail sectors.
""")
    print("Test document created: data/test_doc.txt")

    client   = get_client()
    create_collection(client)
    embedder = get_embedder()

    count = ingest_file("data/test_doc.txt", client, embedder)
    assert count > 0, "No chunks were ingested"

    print(f"\nM1 test PASSED ✓ — {count} chunks ingested")

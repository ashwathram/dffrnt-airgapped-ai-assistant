import sys, hashlib, json, shutil
sys.path.append("..")
from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from config import API_HOST, API_PORT, AUDIT_LOG_PATH
from m2_vectorstore.vector_store import get_client, create_collection
from m4_rag.rag_pipeline import ask

# ── App setup ─────────────────────────────────────────────────────
app = FastAPI(title="DFFRNT AI Assistant")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Database connection ───────────────────────────────────────────
qdrant = get_client()
create_collection(qdrant)

# ── Audit logging ─────────────────────────────────────────────────
Path(AUDIT_LOG_PATH).parent.mkdir(parents=True, exist_ok=True)

def write_audit(event_type: str, data: dict):
    event = {
        "timestamp":  datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        **data
    }
    with open(AUDIT_LOG_PATH, "a") as f:
        f.write(json.dumps(event) + "\n")

# ── Request / Response models ─────────────────────────────────────
class ConversationTurn(BaseModel):
    role:    str   # "user" or "assistant"
    content: str

class QueryRequest(BaseModel):
    question:             str
    conversation_history: List[ConversationTurn] = []

class QueryResponse(BaseModel):
    answer:   str
    sources:  list
    question: str

# ══ ENDPOINTS ════════════════════════════════════════════════════

# ── Health ────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {
        "status":  "running",
        "message": "DFFRNT AI Assistant is online"
    }

# ── Query (FR-01, FR-02, FR-03, FR-05) ───────────────────────────
@app.post("/api/query", response_model=QueryResponse)
def query_endpoint(request: QueryRequest):
    question = request.question.strip()

    # FR-05: reject empty question
    if not question:
        raise HTTPException(400, "Question cannot be empty")
    if len(question) > 2000:
        raise HTTPException(400, "Question too long — max 2000 characters")

    # Convert conversation history to plain dicts
    history = [
        {"role": t.role, "content": t.content}
        for t in request.conversation_history
    ]

    # Run RAG pipeline with history (FR-03)
    result = ask(question, qdrant, history)

    write_audit("QUERY", {
        "question_hash":   hashlib.sha256(question.encode()).hexdigest()[:16],
        "question_length": len(question),
        "sources_count":   len(result["sources"]),
        "history_turns":   len(history),
    })

    return QueryResponse(
        answer=result["answer"],
        sources=result["sources"],
        question=question,
    )

# ── Ingest from server path ───────────────────────────────────────
@app.post("/api/ingest")
def ingest_endpoint(file_path: str):
    if not Path(file_path).exists():
        raise HTTPException(404, f"File not found: {file_path}")
    from m1_ingestion.document_loader import ingest_file
    from m3_llm.llm_client import get_embedder
    chunks = ingest_file(file_path, qdrant, get_embedder())
    write_audit("INGESTION", {
        "file":   Path(file_path).name,
        "chunks": chunks
    })
    return {
        "message": f"Ingested {chunks} chunks from {Path(file_path).name}"
    }

# ── Upload and ingest (FR-09, FR-10, FR-11, FR-12, FR-13, FR-14) ─
@app.post("/api/upload")
async def upload_file(
    file:        UploadFile = File(...),
    uploaded_by: str = Form(default="admin"),
    tags:        str = Form(default=""),
):
    # FR-09 + FR-14: validate file type with clear error
    supported = {".pdf", ".docx", ".pptx", ".txt", ".csv", ".xlsx"}
    filename  = file.filename
    ext       = "." + filename.rsplit(".", 1)[-1].lower() \
                if "." in filename else ""

    if ext not in supported:
        raise HTTPException(400,
            f"'{ext}' files are not supported. "
            f"Please upload one of: PDF, DOCX, PPTX, TXT, CSV or XLSX.")

    # Read file content
    content   = await file.read()
    file_size = len(content)
    save_path = Path(f"data/{filename}")

    # FR-12: Duplicate detection
    if save_path.exists():
        existing_size = save_path.stat().st_size
        if existing_size == file_size:
            return {
                "duplicate": True,
                "warning":   f"'{filename}' already exists with identical "
                             f"content. The file was not re-ingested. "
                             f"Delete the existing version first if you want "
                             f"to replace it.",
                "filename":  filename,
                "success":   False,
            }

    # Save file to disk
    save_path.write_bytes(content)

    # FR-11: Auto-extract metadata
    upload_date = datetime.now(timezone.utc).isoformat()
    file_type   = ext.replace(".", "").upper()
    tag_list    = [t.strip() for t in tags.split(",") if t.strip()]

    metadata = {
        "filename":    filename,
        "file_type":   file_type,
        "file_size":   file_size,
        "upload_date": upload_date,
        "uploaded_by": uploaded_by,
        "tags":        tag_list,
    }
    write_audit("UPLOAD", metadata)

    # Ingest into Qdrant
    from m1_ingestion.document_loader import ingest_file
    from m3_llm.llm_client import get_embedder
    try:
        chunks = ingest_file(str(save_path), qdrant, get_embedder())
        write_audit("INGESTION", {"file": filename, "chunks": chunks})

        # FR-13: Return full confirmation with metadata
        return {
            "success":     True,
            "duplicate":   False,
            "message":     f"'{filename}' uploaded and ingested successfully.",
            "filename":    filename,
            "file_type":   file_type,
            "file_size":   f"{file_size / 1024:.1f} KB",
            "upload_date": upload_date,
            "uploaded_by": uploaded_by,
            "tags":        tag_list,
            "chunks":      chunks,
        }
    except Exception as e:
        # FR-14: User friendly error
        raise HTTPException(500,
            f"'{filename}' was saved but could not be ingested. "
            f"Reason: {str(e)}. "
            f"Please check the file is not corrupted or password-protected.")

# ── Document library (FR-06) ──────────────────────────────────────
@app.get("/api/documents")
def list_documents():
    try:
        col    = qdrant.get_collection(collection_name="dffrnt_documents")
        points = qdrant.scroll(
            collection_name="dffrnt_documents",
            limit=1000,
            with_payload=True,
        )

        # Build document map from stored chunks
        doc_map = {}
        for p in points[0]:
            fname = p.payload.get("filename", "unknown")
            if fname not in doc_map:
                doc_map[fname] = {
                    "filename":    fname,
                    "file_type":   fname.rsplit(".", 1)[-1].upper()
                                   if "." in fname else "Unknown",
                    "chunk_count": 0,
                    "file_path":   f"data/{fname}",
                    "file_size":   "Unknown",
                    "upload_date": "Unknown",
                }
            doc_map[fname]["chunk_count"] += 1

        # Enrich with disk metadata (FR-11)
        for fname, info in doc_map.items():
            path = Path(f"data/{fname}")
            if path.exists():
                stat = path.stat()
                size = stat.st_size
                if size < 1024:
                    info["file_size"] = f"{size} B"
                elif size < 1024 * 1024:
                    info["file_size"] = f"{size/1024:.1f} KB"
                else:
                    info["file_size"] = f"{size/1048576:.1f} MB"
                info["upload_date"] = datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc
                ).strftime("%Y-%m-%d %H:%M UTC")

        documents = sorted(
            doc_map.values(), key=lambda x: x["filename"]
        )
        return {
            "total_chunks":   col.points_count,
            "document_count": len(documents),
            "documents":      documents,
        }
    except Exception:
        return {
            "total_chunks":   0,
            "document_count": 0,
            "documents":      [],
        }

# ── Delete document ───────────────────────────────────────────────
@app.delete("/api/documents/{filename}")
def delete_document(filename: str):
    """Remove a document from disk and from Qdrant."""
    file_path = Path(f"data/{filename}")

    # Remove from Qdrant by filtering on filename
    try:
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        qdrant.delete(
            collection_name="dffrnt_documents",
            points_selector=Filter(
                must=[FieldCondition(
                    key="filename",
                    match=MatchValue(value=filename)
                )]
            )
        )
    except Exception as e:
        raise HTTPException(500, f"Could not remove from index: {str(e)}")

    # Remove from disk
    if file_path.exists():
        file_path.unlink()

    write_audit("DELETION", {"filename": filename})
    return {"message": f"'{filename}' deleted successfully."}

# ── Run ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    print(f"Starting DFFRNT AI on {API_HOST}:{API_PORT}")
    uvicorn.run(app, host=API_HOST, port=API_PORT)

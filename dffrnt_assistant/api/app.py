"""FastAPI presentation layer: HTTP wiring only. Business logic is in services.py."""

from pathlib import Path
from typing import List

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..config import load_settings
from ..ollama import OllamaClient
from ..rag.pipeline import RagPipeline
from ..retrieval.retriever import Retriever
from ..retrieval.store import VectorStore
from .audit import AuditLog
from .services import AssistantService, UserError

settings = load_settings()

# Build the long-lived components once, at startup.
store = VectorStore(
    settings.qdrant_url, settings.collection_name, settings.vector_size, settings.distance
)
store.ensure_collection()
ollama = OllamaClient(
    settings.ollama_url,
    settings.llm_model,
    settings.embed_model,
    settings.llm_temperature,
    settings.llm_timeout,
)
retriever = Retriever(store, ollama, settings)
rag = RagPipeline(retriever, ollama, settings)
audit = AuditLog(settings.audit_log_path)
service = AssistantService(settings, store, ollama, rag, audit)

UI_FILE = Path(__file__).resolve().parent.parent / "ui" / "index.html"

app = FastAPI(title="DFFRNT AI Assistant")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


class ConversationTurn(BaseModel):
    role: str
    content: str


class QueryRequest(BaseModel):
    question: str
    conversation_history: List[ConversationTurn] = []


class QueryResponse(BaseModel):
    answer: str
    sources: list
    question: str


class IngestRequest(BaseModel):
    file_path: str


def _handle(call):
    """Run a service call, mapping UserError to the matching HTTP status."""
    try:
        return call()
    except UserError as exc:
        raise HTTPException(exc.status_code, exc.detail)


@app.get("/")
def serve_ui():
    return FileResponse(str(UI_FILE))


@app.get("/health")
def health():
    return {"status": "running", "message": "DFFRNT AI Assistant is online"}


@app.post("/api/query", response_model=QueryResponse)
def query_endpoint(request: QueryRequest):
    history = [turn.model_dump() for turn in request.conversation_history]
    return _handle(lambda: service.query(request.question, history))


@app.post("/api/ingest")
def ingest_endpoint(request: IngestRequest):
    return _handle(lambda: service.ingest_path(request.file_path))


@app.post("/api/upload")
async def upload_file(
    file: UploadFile = File(...),
    uploaded_by: str = Form(default="admin"),
    tags: str = Form(default=""),
):
    content = await file.read()
    return _handle(lambda: service.upload(file.filename, content, uploaded_by, tags))


@app.get("/api/documents")
def list_documents():
    return service.list_documents()


@app.delete("/api/documents/{filename}")
def delete_document(filename: str):
    return _handle(lambda: service.delete(filename))


def main():
    import uvicorn

    print(
        f"Starting DFFRNT AI Assistant on {settings.api_host}:{settings.api_port} "
        f"(env={settings.environment}, model={settings.llm_model})"
    )
    uvicorn.run(app, host=settings.api_host, port=settings.api_port)


if __name__ == "__main__":
    main()

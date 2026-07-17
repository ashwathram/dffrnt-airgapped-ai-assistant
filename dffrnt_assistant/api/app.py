"""FastAPI presentation layer: HTTP wiring only. Business logic is in services.py."""

import json
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..config import load_settings
from ..ollama import OllamaClient
from ..rag import RagPipeline
from ..retrieval.doc_store import ConversationStore, TagStore
from ..retrieval.retriever import Retriever
from ..retrieval.store import VectorStore
from . import export
from .audit import AuditLog
from .services import AssistantService, ConversationService, TagService, UserError

settings = load_settings()

# Build the long-lived components once, at startup.
store = VectorStore(
    settings.qdrant_url, settings.collection_name, settings.vector_size, settings.distance
)
store.ensure_collection()
summary_store = VectorStore(
    settings.qdrant_url,
    settings.summary_collection_name,
    settings.vector_size,
    settings.distance,
)
summary_store.ensure_collection()
ollama = OllamaClient(
    settings.ollama_url,
    settings.llm_model,
    settings.embed_model,
    settings.llm_temperature,
    settings.llm_timeout,
    settings.embed_query_prefix,
    settings.embed_document_prefix,
    settings.llm_num_ctx,
    settings.llm_top_p,
    settings.llm_top_k,
    settings.llm_repeat_penalty,
    settings.llm_num_predict,
    settings.embed_on_cpu,
)
audit = AuditLog(settings.audit_log_path)
retriever = Retriever(store, ollama, settings, summary_store=summary_store, audit=audit)
rag = RagPipeline(retriever, ollama, settings, audit=audit)
service = AssistantService(settings, store, summary_store, ollama, rag, audit)

tag_store = TagStore(settings.qdrant_url, settings.tags_collection_name)
tag_store.ensure_collection()
tag_service = TagService(tag_store)

conversation_store = ConversationStore(
    settings.qdrant_url, settings.conversations_collection_name
)
conversation_store.ensure_collection()
conversation_service = ConversationService(conversation_store)

UI_DIR = Path(__file__).resolve().parent.parent / "ui"
UI_FILE = UI_DIR / "index.html"


def _warmup_worker():
    """Preload the LLM + embedder so the first user query skips the model-load
    stall. Runs in a daemon thread at every API start — including container
    restarts after a host reboot, which bypass dffrnt_ctrl_panel.sh — and
    retries while the stack boots (on a first online deploy the models may
    still be pulling). Gives up quietly after ~10 minutes; the app works
    either way, the first query just pays the load."""
    t0 = time.perf_counter()
    for attempt in range(1, 21):
        try:
            ollama.warmup()
            audit.write(
                "WARMUP",
                {"attempts": attempt, "ms": round((time.perf_counter() - t0) * 1000, 2)},
            )
            return
        except Exception:
            time.sleep(30)
    audit.write("WARMUP", {"attempts": 20, "failed": True})


@asynccontextmanager
async def lifespan(_app: FastAPI):
    threading.Thread(target=_warmup_worker, name="ollama-warmup", daemon=True).start()
    yield


# No CORS middleware: the UI is served same-origin from this app, and the API
# is not meant to be called from other origins.
app = FastAPI(title="DFFRNT AI Assistant", lifespan=lifespan)

app.mount("/ui", StaticFiles(directory=str(UI_DIR)), name="ui")


class ConversationTurn(BaseModel):
    role: str
    content: str


class QueryRequest(BaseModel):
    question: str
    conversation_history: List[ConversationTurn] = []
    tags: List[str] = []  # restrict retrieval to documents carrying any of these tags


class QueryResponse(BaseModel):
    answer: str
    sources: list
    question: str


class ExportRequest(BaseModel):
    content: str            # the answer's Markdown text
    title: str = ""         # optional heading printed at the top of the PDF


class TagTypeRequest(BaseModel):
    name: str
    color: str = "#5D27B8"
    description: Optional[str] = None


class TagRequest(BaseModel):
    name: str
    type_id: str


class DocTagsRequest(BaseModel):
    tags: List[str] = []


class DocDescriptionRequest(BaseModel):
    description: str = ""


class ConversationCreate(BaseModel):
    title: str = ""
    messages: list = []


class ConversationUpdate(BaseModel):
    title: Optional[str] = None
    messages: Optional[list] = None
    pinned: Optional[bool] = None


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
    return _handle(lambda: service.query(request.question, history, request.tags))


@app.post("/api/query/stream")
def query_stream_endpoint(request: QueryRequest):
    """Stream the answer as ndjson: one ``sources`` line, then ``thinking`` /
    ``token`` lines, ending with ``done`` (or ``error`` on mid-stream failure)."""
    history = [turn.model_dump() for turn in request.conversation_history]
    # Validation errors surface here (before streaming) as a normal HTTP error.
    events = _handle(lambda: service.query_stream(request.question, history, request.tags))

    line_type = {"sources": "sources", "thinking": "thinking", "token": "token"}

    def ndjson():
        try:
            for kind, payload in events:
                if kind == "sources":
                    yield json.dumps({"type": "sources", "sources": payload}) + "\n"
                else:
                    yield json.dumps({"type": line_type[kind], "text": payload}) + "\n"
            yield json.dumps({"type": "done"}) + "\n"
        except Exception as exc:  # generation failed mid-stream
            yield json.dumps({"type": "error", "detail": str(exc)}) + "\n"

    return StreamingResponse(ndjson(), media_type="application/x-ndjson")


@app.post("/api/export/pdf")
def export_pdf(request: ExportRequest):
    """Render an answer's Markdown to a PDF. TXT/MD exports are client-side;
    only PDF needs a server round-trip."""
    pdf = export.markdown_to_pdf(request.content, request.title)
    return Response(content=pdf, media_type="application/pdf")


@app.post("/api/upload")
async def upload_file(
    file: UploadFile = File(...),
    tags: str = Form(default=""),
    description: str = Form(default=""),
    force: bool = Form(default=False),
):
    content = await file.read()
    return _handle(
        lambda: service.upload(file.filename, content, tags, description, force)
    )


@app.post("/api/upload/stream")
async def upload_file_stream(
    file: UploadFile = File(...),
    tags: str = Form(default=""),
    description: str = Form(default=""),
    force: bool = Form(default=False),
):
    """Upload + ingest, streaming ndjson progress events per real stage
    (parsing / chunking / embedding / storing), ending with ``done``."""
    content = await file.read()

    def ndjson():
        try:
            for event in service.upload_stream(file.filename, content, tags, description, force):
                yield json.dumps(event) + "\n"
        except Exception as exc:  # unexpected failure mid-stream
            yield json.dumps({"stage": "error", "detail": str(exc)}) + "\n"

    return StreamingResponse(ndjson(), media_type="application/x-ndjson")


@app.get("/api/documents")
def list_documents():
    return service.list_documents()


@app.delete("/api/documents/{filename}")
def delete_document(filename: str):
    return _handle(lambda: service.delete(filename))


@app.put("/api/documents/{filename}/tags")
def update_document_tags(filename: str, body: DocTagsRequest):
    return _handle(lambda: service.update_tags(filename, body.tags))


@app.put("/api/documents/{filename}/description")
def update_document_description(filename: str, body: DocDescriptionRequest):
    return _handle(lambda: service.update_description(filename, body.description))


@app.get("/api/documents/{filename}/raw")
def get_document_file(filename: str):
    """Serve the stored file so citations can hotlink to it (inline preview)."""
    path = _handle(lambda: service.file_path(filename))
    return FileResponse(str(path))


# -- Tag taxonomy: every mutation returns the full updated taxonomy ---------
@app.get("/api/tags")
def get_tags():
    return tag_service.get()


@app.post("/api/tags/types")
def add_tag_type(body: TagTypeRequest):
    return _handle(lambda: tag_service.add_type(body.name, body.color, body.description))


@app.put("/api/tags/types/{type_id}")
def update_tag_type(type_id: str, body: TagTypeRequest):
    return _handle(lambda: tag_service.update_type(type_id, body.name, body.color, body.description))


@app.delete("/api/tags/types/{type_id}")
def delete_tag_type(type_id: str):
    return _handle(lambda: tag_service.delete_type(type_id))


@app.post("/api/tags/import")
def import_document_tags():
    """Seed the taxonomy from tag strings already attached to ingested documents."""
    names = service.distinct_document_tags()
    return _handle(lambda: tag_service.import_names(names))


@app.post("/api/tags/tags")
def add_tag(body: TagRequest):
    return _handle(lambda: tag_service.add_tag(body.name, body.type_id))


@app.delete("/api/tags/tags/{tag_id}")
def delete_tag(tag_id: str):
    return _handle(lambda: tag_service.delete_tag(tag_id))


# -- Conversations (saved chat history) -------------------------------------
@app.get("/api/conversations")
def list_conversations():
    return conversation_service.list()


@app.post("/api/conversations")
def create_conversation(body: ConversationCreate):
    return _handle(lambda: conversation_service.create(body.title, body.messages))


@app.delete("/api/conversations")
def clear_conversations():
    return conversation_service.clear()


@app.get("/api/conversations/{conversation_id}")
def get_conversation(conversation_id: str):
    return _handle(lambda: conversation_service.get(conversation_id))


@app.put("/api/conversations/{conversation_id}")
def update_conversation(conversation_id: str, body: ConversationUpdate):
    return _handle(
        lambda: conversation_service.update(
            conversation_id, body.title, body.messages, body.pinned
        )
    )


@app.delete("/api/conversations/{conversation_id}")
def delete_conversation(conversation_id: str):
    return _handle(lambda: conversation_service.delete(conversation_id))


def main():
    import uvicorn

    print(
        f"Starting DFFRNT AI Assistant on {settings.api_host}:{settings.api_port} "
        f"(gpu={settings.gpu}, model={settings.llm_model})"
    )
    uvicorn.run(app, host=settings.api_host, port=settings.api_port)


if __name__ == "__main__":
    main()

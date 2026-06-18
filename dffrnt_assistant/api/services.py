"""Application services: all upload / query / library / delete logic lives here,
so the FastAPI layer stays a thin HTTP adapter."""

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from ..ingest.pipeline import SUPPORTED_EXTENSIONS, ingest_file
from ..ingest.tags import normalize_tag_payload


class UserError(Exception):
    """A client-facing error carrying an HTTP status code."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _human_size(num_bytes: int) -> str:
    if num_bytes < 1024:
        return f"{num_bytes} B"
    if num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} KB"
    return f"{num_bytes / 1048576:.1f} MB"


class AssistantService:
    def __init__(self, settings, store, embedder, rag, audit):
        self.settings = settings
        self.store = store
        self.embedder = embedder
        self.rag = rag
        self.audit = audit
        self.data_dir = Path(settings.data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    # -- Query -------------------------------------------------------------
    def query(self, question: str, history: Optional[List[dict]] = None) -> dict:
        question = (question or "").strip()
        if not question:
            raise UserError(400, "Question cannot be empty")
        if len(question) > 2000:
            raise UserError(400, "Question too long — max 2000 characters")

        history = history or []
        result = self.rag.answer(question, history)
        self.audit.write(
            "QUERY",
            {
                "question_hash": hashlib.sha256(question.encode()).hexdigest()[:16],
                "question_length": len(question),
                "sources_count": len(result["sources"]),
                "history_turns": len(history),
            },
        )
        return result

    # -- Ingestion ---------------------------------------------------------
    def _ingest(self, path: Path, meta: Optional[dict] = None) -> int:
        chunks = ingest_file(path, self.store, self.embedder, self.settings, meta)
        self.audit.write("INGESTION", {"file": path.name, "chunks": chunks})
        return chunks

    def ingest_path(self, file_path: str) -> dict:
        path = Path(file_path)
        if not path.exists():
            raise UserError(404, f"File not found: {file_path}")
        chunks = self._ingest(path)
        return {"message": f"Ingested {chunks} chunks from {path.name}"}

    def upload(self, filename: str, content: bytes, uploaded_by: str, tags: str) -> dict:
        ext = Path(filename).suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            allowed = ", ".join(sorted(e[1:].upper() for e in SUPPORTED_EXTENSIONS))
            raise UserError(400, f"'{ext}' files are not supported. Please upload one of: {allowed}.")

        save_path = self.data_dir / filename

        # A real duplicate is one already *ingested* (in the vector store) with
        # identical content — not merely a leftover file on disk. This lets users
        # (re-)ingest files that exist on disk but aren't in the knowledge base.
        if save_path.exists() and self.store.has_document(filename):
            existing_hash = hashlib.sha256(save_path.read_bytes()).hexdigest()
            if existing_hash == hashlib.sha256(content).hexdigest():
                return {
                    "duplicate": True,
                    "success": False,
                    "filename": filename,
                    "warning": (
                        f"'{filename}' is already in the knowledge base with identical "
                        f"content. It was not re-ingested. Delete the existing version "
                        f"first to replace it."
                    ),
                }

        save_path.write_bytes(content)

        tag_items = [t.strip() for t in tags.split(",") if t.strip()]
        leaf_tags, tag_paths = normalize_tag_payload(tag_items)
        meta = {"tags": leaf_tags, "tag_paths": tag_paths} if leaf_tags else None

        upload_date = datetime.now(timezone.utc).isoformat()
        file_size = len(content)
        file_type = ext[1:].upper()
        self.audit.write(
            "UPLOAD",
            {
                "filename": filename,
                "file_type": file_type,
                "file_size": file_size,
                "upload_date": upload_date,
                "uploaded_by": uploaded_by,
                "tags": leaf_tags,
            },
        )

        try:
            chunks = self._ingest(save_path, meta)
        except Exception as exc:
            raise UserError(
                500,
                f"'{filename}' was saved but could not be ingested. Reason: {exc}. "
                f"Please check the file is not corrupted or password-protected.",
            )

        return {
            "success": True,
            "duplicate": False,
            "message": f"'{filename}' uploaded and ingested successfully.",
            "filename": filename,
            "file_type": file_type,
            "file_size": _human_size(file_size),
            "upload_date": upload_date,
            "uploaded_by": uploaded_by,
            "tags": leaf_tags,
            "chunks": chunks,
        }

    # -- Library -----------------------------------------------------------
    def list_documents(self) -> dict:
        documents: dict = {}
        for payload in self.store.all_payloads():
            payload = payload or {}
            filename = payload.get("filename", "unknown")
            entry = documents.setdefault(
                filename,
                {
                    "filename": filename,
                    "file_type": (
                        payload.get("file_type")
                        or (filename.rsplit(".", 1)[-1] if "." in filename else "")
                    ).upper(),
                    "chunk_count": 0,
                    "file_path": str(self.data_dir / filename),
                    "file_size": "Unknown",
                    "upload_date": "Unknown",
                },
            )
            entry["chunk_count"] += 1

        for filename, info in documents.items():
            path = self.data_dir / filename
            if path.exists():
                stat = path.stat()
                info["file_size"] = _human_size(stat.st_size)
                info["upload_date"] = datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc
                ).strftime("%Y-%m-%d %H:%M UTC")

        return {
            "total_chunks": self.store.count(),
            "document_count": len(documents),
            "documents": sorted(documents.values(), key=lambda d: d["filename"]),
        }

    # -- Deletion ----------------------------------------------------------
    def delete(self, filename: str) -> dict:
        self.store.delete_by_filename(filename)
        path = self.data_dir / filename
        if path.exists():
            path.unlink()
        self.audit.write("DELETION", {"filename": filename})
        return {"message": f"'{filename}' deleted successfully."}

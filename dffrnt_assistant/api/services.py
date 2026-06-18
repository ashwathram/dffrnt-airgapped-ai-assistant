"""Application services: all upload / query / library / delete logic lives here,
so the FastAPI layer stays a thin HTTP adapter."""

import hashlib
import time
import uuid
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
    def query(
        self, question: str, history: Optional[List[dict]] = None, tags: Optional[List[str]] = None
    ) -> dict:
        question = (question or "").strip()
        if not question:
            raise UserError(400, "Question cannot be empty")
        if len(question) > 2000:
            raise UserError(400, "Question too long — max 2000 characters")

        history = history or []
        tag_filter = [t for t in (tags or []) if t]
        result = self.rag.answer(question, history, tag_filter)
        self.audit.write(
            "QUERY",
            {
                "question_hash": hashlib.sha256(question.encode()).hexdigest()[:16],
                "question_length": len(question),
                "sources_count": len(result["sources"]),
                "history_turns": len(history),
                "tag_filter": tag_filter,
            },
        )
        return result

    def query_stream(
        self, question: str, history: Optional[List[dict]] = None, tags: Optional[List[str]] = None
    ):
        """Like ``query`` but streams ``(kind, payload)`` events.

        Validation runs eagerly (before any event is produced) so the HTTP layer
        can return a proper error status before the stream starts. The audit
        record is written once the stream is fully consumed.
        """
        question = (question or "").strip()
        if not question:
            raise UserError(400, "Question cannot be empty")
        if len(question) > 2000:
            raise UserError(400, "Question too long — max 2000 characters")
        history = history or []
        tag_filter = [t for t in (tags or []) if t]

        def events():
            sources_count = 0
            answer_length = 0
            for kind, payload in self.rag.answer_stream(question, history, tag_filter):
                if kind == "sources":
                    sources_count = len(payload)
                elif kind == "token":
                    answer_length += len(payload)
                yield kind, payload
            self.audit.write(
                "QUERY",
                {
                    "question_hash": hashlib.sha256(question.encode()).hexdigest()[:16],
                    "question_length": len(question),
                    "sources_count": sources_count,
                    "answer_length": answer_length,
                    "history_turns": len(history),
                    "tag_filter": tag_filter,
                    "streamed": True,
                },
            )

        return events()

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
        tagsets: dict = {}  # filename -> set of tag strings (chunks share tags)
        mtimes: dict = {}   # filename -> file mtime, for newest-first ordering
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
                    "tags": [],
                },
            )
            entry["chunk_count"] += 1
            tagsets.setdefault(filename, set()).update(payload.get("tags") or [])

        for filename, info in documents.items():
            info["tags"] = sorted(tagsets.get(filename, set()))
            path = self.data_dir / filename
            if path.exists():
                stat = path.stat()
                mtimes[filename] = stat.st_mtime
                info["file_size"] = _human_size(stat.st_size)
                info["upload_date"] = datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc
                ).strftime("%Y-%m-%d %H:%M UTC")

        return {
            "total_chunks": self.store.count(),
            "document_count": len(documents),
            # Newest first; documents whose file is missing (mtime 0) sort last.
            "documents": sorted(
                documents.values(),
                key=lambda d: mtimes.get(d["filename"], 0.0),
                reverse=True,
            ),
        }

    # -- Deletion ----------------------------------------------------------
    def delete(self, filename: str) -> dict:
        self.store.delete_by_filename(filename)
        path = self.data_dir / filename
        if path.exists():
            path.unlink()
        self.audit.write("DELETION", {"filename": filename})
        return {"message": f"'{filename}' deleted successfully."}

    # -- File access -------------------------------------------------------
    def file_path(self, filename: str) -> Path:
        """Resolve an uploaded file on disk for download/preview. Only files
        directly inside data_dir are served (guards against path traversal)."""
        path = self.data_dir / Path(filename).name
        if not path.is_file():
            raise UserError(404, f"File not found: {filename}")
        return path

    # -- Tag assignment ----------------------------------------------------
    def update_tags(self, filename: str, tags: List[str]) -> dict:
        """Set a document's tags by rewriting the tags/tag_paths on every chunk."""
        if not self.store.has_document(filename):
            raise UserError(404, f"Document not found: {filename}")
        leaf_tags, tag_paths = normalize_tag_payload(tags)
        self.store.set_payload_by_filename(
            filename, {"tags": leaf_tags, "tag_paths": tag_paths}
        )
        self.audit.write("TAG_UPDATE", {"filename": filename, "tags": leaf_tags})
        return {"filename": filename, "tags": leaf_tags}

    # -- Tags --------------------------------------------------------------
    def distinct_document_tags(self) -> List[str]:
        """Distinct leaf tag strings across all ingested documents.

        Used to seed the tag taxonomy from tags already attached to documents.
        """
        seen: dict = {}
        for payload in self.store.all_payloads():
            for tag in (payload or {}).get("tags", []) or []:
                name = str(tag).strip()
                if name:
                    seen.setdefault(name.lower(), name)  # keep first-seen casing
        return sorted(seen.values(), key=str.lower)


def _clean_name(value: str, label: str = "Name") -> str:
    name = (value or "").strip()
    if not name:
        raise UserError(400, f"{label} cannot be empty")
    if len(name) > 60:
        raise UserError(400, f"{label} too long — max 60 characters")
    return name


class TagService:
    """CRUD for the tag taxonomy (tag types + tags), persisted via TagStore.

    The taxonomy is a single blob, so every mutation is read-modify-write:
    load it, change it, validate, save it, and return the fresh taxonomy so the
    UI can replace its state in one step.
    """

    def __init__(self, tag_store):
        self.store = tag_store

    def get(self) -> dict:
        return self.store.load()

    # -- Tag types ---------------------------------------------------------
    def add_type(self, name: str, color: str, description: Optional[str]) -> dict:
        name = _clean_name(name, "Tag type name")
        tax = self.store.load()
        if any(t["name"].lower() == name.lower() for t in tax["tag_types"]):
            raise UserError(409, f"A tag type named '{name}' already exists")
        tax["tag_types"].append({
            "id": f"tt-{uuid.uuid4().hex[:8]}",
            "name": name,
            "color": (color or "#5D27B8").strip(),
            "description": (description or "").strip() or None,
        })
        self.store.save(tax)
        return tax

    def update_type(self, type_id: str, name: str, color: str, description: Optional[str]) -> dict:
        name = _clean_name(name, "Tag type name")
        tax = self.store.load()
        target = next((t for t in tax["tag_types"] if t["id"] == type_id), None)
        if target is None:
            raise UserError(404, "Tag type not found")
        if any(t["id"] != type_id and t["name"].lower() == name.lower() for t in tax["tag_types"]):
            raise UserError(409, f"A tag type named '{name}' already exists")
        target.update({
            "name": name,
            "color": (color or target["color"]).strip(),
            "description": (description or "").strip() or None,
        })
        self.store.save(tax)
        return tax

    def delete_type(self, type_id: str) -> dict:
        tax = self.store.load()
        if not any(t["id"] == type_id for t in tax["tag_types"]):
            raise UserError(404, "Tag type not found")
        # Cascade: a tag cannot outlive its type.
        tax["tag_types"] = [t for t in tax["tag_types"] if t["id"] != type_id]
        tax["tags"] = [t for t in tax["tags"] if t["typeId"] != type_id]
        self.store.save(tax)
        return tax

    # -- Tags --------------------------------------------------------------
    def add_tag(self, name: str, type_id: str) -> dict:
        name = _clean_name(name, "Tag name")
        tax = self.store.load()
        if not any(t["id"] == type_id for t in tax["tag_types"]):
            raise UserError(404, "Tag type not found")
        if any(t["typeId"] == type_id and t["name"].lower() == name.lower() for t in tax["tags"]):
            raise UserError(409, f"A tag named '{name}' already exists in this type")
        tax["tags"].append({
            "id": f"t-{uuid.uuid4().hex[:8]}",
            "name": name,
            "typeId": type_id,
        })
        self.store.save(tax)
        return tax

    def delete_tag(self, tag_id: str) -> dict:
        tax = self.store.load()
        if not any(t["id"] == tag_id for t in tax["tags"]):
            raise UserError(404, "Tag not found")
        tax["tags"] = [t for t in tax["tags"] if t["id"] != tag_id]
        self.store.save(tax)
        return tax

    # -- Bulk import -------------------------------------------------------
    def import_names(self, names: List[str], type_name: str = "Imported") -> dict:
        """Idempotently add tag strings under a single type.

        Reuses the type if one with this name already exists, and skips tags
        that are already present — so re-running is safe. Returns the fresh
        taxonomy plus how many tags were newly imported.
        """
        tax = self.store.load()
        target = next(
            (t for t in tax["tag_types"] if t["name"].lower() == type_name.lower()), None
        )
        if target is None:
            target = {
                "id": f"tt-{uuid.uuid4().hex[:8]}",
                "name": type_name,
                "color": "#5D27B8",
                "description": "Imported from document tags",
            }
            tax["tag_types"].append(target)

        existing = {t["name"].lower() for t in tax["tags"] if t["typeId"] == target["id"]}
        imported = 0
        for raw in names:
            name = (raw or "").strip()
            if not name or name.lower() in existing:
                continue
            tax["tags"].append(
                {"id": f"t-{uuid.uuid4().hex[:8]}", "name": name, "typeId": target["id"]}
            )
            existing.add(name.lower())
            imported += 1

        self.store.save(tax)
        return {"imported": imported, "type": target["name"], **tax}


class ConversationService:
    """CRUD for saved conversations, persisted via ConversationStore."""

    def __init__(self, conversation_store):
        self.store = conversation_store

    def list(self) -> dict:
        """Light list for the sidebar (no message bodies), pinned first then
        most-recently-updated."""
        items = [
            {
                "id": c["id"],
                "title": c.get("title", "Untitled"),
                "updated_at": c.get("updated_at", 0),
                "pinned": bool(c.get("pinned", False)),
            }
            for c in self.store.list()
        ]
        items.sort(key=lambda c: (not c["pinned"], -c["updated_at"]))
        return {"conversations": items}

    def get(self, conversation_id: str) -> dict:
        convo = self.store.get(conversation_id)
        if convo is None:
            raise UserError(404, "Conversation not found")
        return convo

    def create(self, title: str, messages: Optional[list]) -> dict:
        now = time.time()
        convo = {
            "id": str(uuid.uuid4()),
            "title": (title or "").strip()[:80] or "New conversation",
            "messages": messages or [],
            "created_at": now,
            "updated_at": now,
            "pinned": False,
        }
        self.store.save(convo)
        return convo

    def update(
        self,
        conversation_id: str,
        title: Optional[str] = None,
        messages: Optional[list] = None,
        pinned: Optional[bool] = None,
    ) -> dict:
        convo = self.store.get(conversation_id)
        if convo is None:
            raise UserError(404, "Conversation not found")
        if title is not None:
            cleaned = title.strip()[:80]
            if cleaned:
                convo["title"] = cleaned
        if messages is not None:
            convo["messages"] = messages
        if pinned is not None:
            convo["pinned"] = bool(pinned)
        convo["updated_at"] = time.time()
        self.store.save(convo)
        return convo

    def delete(self, conversation_id: str) -> dict:
        if self.store.get(conversation_id) is None:
            raise UserError(404, "Conversation not found")
        self.store.delete(conversation_id)
        return {"deleted": conversation_id}

    def clear(self) -> dict:
        return {"cleared": self.store.clear()}

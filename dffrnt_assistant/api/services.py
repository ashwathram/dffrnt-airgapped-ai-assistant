"""Application services: all upload / query / library / delete logic lives here,
so the FastAPI layer stays a thin HTTP adapter."""

import hashlib
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from ..ingest.pipeline import SUPPORTED_EXTENSIONS, ingest_file, ingest_file_stream
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
    def __init__(self, settings, store, summary_store, embedder, rag, audit):
        self.settings = settings
        self.store = store
        self.summary_store = summary_store
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
        chunks = ingest_file(
            path,
            self.store,
            self.embedder,
            self.settings,
            meta,
            summary_store=self.summary_store,
        )
        self.audit.write("INGESTION", {"file": path.name, "chunks": chunks})
        return chunks

    def _prepare_upload(
        self, filename: str, content: bytes, tags: str,
        description: str, force: bool,
    ):
        """Validate, dedup-check, persist the bytes and build the ingest meta.

        Returns ``("duplicate", dup_dict)`` when the caller should stop and
        report a duplicate, or ``("ready", ctx)`` where ``ctx`` carries the
        saved path, meta and display fields the ingest + result share. Raises
        :class:`UserError` for unsupported types.
        """
        ext = Path(filename).suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            allowed = ", ".join(sorted(e[1:].upper() for e in SUPPORTED_EXTENSIONS))
            raise UserError(400, f"'{ext}' files are not supported. Please upload one of: {allowed}.")

        save_path = self.data_dir / filename
        content_hash = hashlib.sha256(content).hexdigest()

        # Duplicate detection (skipped when the caller forces the upload, e.g.
        # the user chose "Keep both"). Two kinds:
        #   name    — same filename already ingested with identical content
        #   content — byte-identical content already ingested under another name
        if not force:
            if (
                save_path.exists()
                and self.store.has_document(filename)
                and hashlib.sha256(save_path.read_bytes()).hexdigest() == content_hash
            ):
                return "duplicate", {
                    "duplicate": True, "kind": "name", "success": False,
                    "filename": filename, "existing": filename,
                    "warning": (
                        f"'{filename}' is already in the knowledge base with identical "
                        f"content. Replace it, keep both, or skip."
                    ),
                }
            content_dup = self.store.find_by_content_hash(content_hash)
            if content_dup and content_dup != filename:
                return "duplicate", {
                    "duplicate": True, "kind": "content", "success": False,
                    "filename": filename, "existing": content_dup,
                    "warning": (
                        f"'{filename}' has the same content as '{content_dup}', which is "
                        f"already in the knowledge base. Replace it, keep both, or skip."
                    ),
                }

        save_path.write_bytes(content)

        tag_items = [t.strip() for t in tags.split(",") if t.strip()]
        leaf_tags, tag_paths = normalize_tag_payload(tag_items)
        # description/content_hash are stored on every chunk (like tags) so the
        # library can show them, dedup can match later uploads, and they survive
        # re-reads of the vector store.
        description = (description or "").strip()
        meta = {
            "description": description,
            "content_hash": content_hash,
        }
        if leaf_tags:
            meta["tags"] = leaf_tags
            meta["tag_paths"] = tag_paths

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
                "description": description,
                "tags": leaf_tags,
            },
        )
        return "ready", {
            "save_path": save_path, "meta": meta, "filename": filename,
            "file_type": file_type, "file_size": file_size, "upload_date": upload_date,
            "description": description, "leaf_tags": leaf_tags,
        }

    def _upload_result(self, ctx: dict, chunks: int) -> dict:
        return {
            "success": True,
            "duplicate": False,
            "message": f"'{ctx['filename']}' uploaded and ingested successfully.",
            "filename": ctx["filename"],
            "file_type": ctx["file_type"],
            "file_size": _human_size(ctx["file_size"]),
            "upload_date": ctx["upload_date"],
            "description": ctx["description"],
            "tags": ctx["leaf_tags"],
            "chunks": chunks,
        }

    def upload(
        self, filename: str, content: bytes, tags: str,
        description: str = "", force: bool = False,
    ) -> dict:
        kind, data = self._prepare_upload(filename, content, tags, description, force)
        if kind == "duplicate":
            return data
        try:
            chunks = self._ingest(data["save_path"], data["meta"])
        except Exception as exc:
            raise UserError(
                500,
                f"'{filename}' was saved but could not be ingested. Reason: {exc}. "
                f"Please check the file is not corrupted or password-protected.",
            )
        return self._upload_result(data, chunks)

    def upload_stream(
        self, filename: str, content: bytes, tags: str,
        description: str = "", force: bool = False,
    ):
        """Upload + ingest, yielding progress events (see ingest_file_stream).

        Emits ``{"stage": ...}`` dicts the caller can serialise as ndjson:
        ``received`` (bytes persisted), ``parsing`` / ``chunking`` /
        ``embedding`` (with done/total) / ``storing`` from ingestion, then a
        terminal ``done`` (carrying the full result) — or ``duplicate`` /
        ``error``. Lets the UI show a bar tied to the real (embedding) stage.
        """
        try:
            kind, data = self._prepare_upload(filename, content, tags, description, force)
        except UserError as exc:
            yield {"stage": "error", "detail": exc.detail}
            return
        if kind == "duplicate":
            yield {"stage": "duplicate", **data}
            return

        yield {"stage": "received", "size": data["file_size"]}
        chunks = 0
        try:
            for event in ingest_file_stream(
                data["save_path"],
                self.store,
                self.embedder,
                self.settings,
                data["meta"],
                summary_store=self.summary_store,
            ):
                if event.get("stage") == "stored":
                    chunks = event["chunks"]
                else:
                    yield event
        except Exception as exc:
            yield {
                "stage": "error",
                "detail": (
                    f"'{filename}' was saved but could not be ingested. Reason: {exc}. "
                    f"Please check the file is not corrupted or password-protected."
                ),
            }
            return
        self.audit.write("INGESTION", {"file": data["save_path"].name, "chunks": chunks})
        yield {"stage": "done", "result": self._upload_result(data, chunks)}

    # -- Library -----------------------------------------------------------
    def list_documents(self) -> dict:
        documents: dict = {}
        tagsets: dict = {}  # filename -> set of tag strings (chunks share tags)
        mtimes: dict = {}   # filename -> file mtime, for newest-first ordering
        text_bytes = 0      # total chunk text held in the vector store
        doc_text: dict = {} # filename -> chunk text bytes for that document
        for payload in self.store.all_payloads():
            payload = payload or {}
            chunk_text_bytes = len((payload.get("text") or "").encode("utf-8"))
            text_bytes += chunk_text_bytes
            filename = payload.get("filename", "unknown")
            doc_text[filename] = doc_text.get(filename, 0) + chunk_text_bytes
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
                    "description": payload.get("description") or "",
                    "tags": [],
                },
            )
            entry["chunk_count"] += 1
            tagsets.setdefault(filename, set()).update(payload.get("tags") or [])

        repo_bytes = 0      # total size of the stored source files on disk
        for filename, info in documents.items():
            info["tags"] = sorted(tagsets.get(filename, set()))
            # Bytes this document occupies in the vector store: its chunk text
            # plus its embedding vectors (chunk_count × dims × 4 bytes, float32).
            info["stored_bytes"] = (
                doc_text.get(filename, 0)
                + info["chunk_count"] * self.store.vector_size * 4
            )
            path = self.data_dir / filename
            if path.exists():
                stat = path.stat()
                mtimes[filename] = stat.st_mtime
                repo_bytes += stat.st_size
                info["file_size"] = _human_size(stat.st_size)
                info["upload_date"] = datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc
                ).strftime("%Y-%m-%d %H:%M UTC")

        total_chunks = self.store.count()
        return {
            "total_chunks": total_chunks,
            "document_count": len(documents),
            "storage": self._storage_stats(total_chunks, text_bytes, repo_bytes),
            # Newest first; documents whose file is missing (mtime 0) sort last.
            "documents": sorted(
                documents.values(),
                key=lambda d: mtimes.get(d["filename"], 0.0),
                reverse=True,
            ),
        }

    def _storage_stats(self, total_chunks: int, text_bytes: int, repo_bytes: int) -> dict:
        """Knowledge-base storage usage vs. the space available to the app.

        Used = the vector store (embedding vectors + chunk text) plus the source
        document repository on disk. The cap is that usage plus the free space
        remaining on the volume the app writes to, so the bar reflects real disk
        pressure rather than a hardcoded quota.
        """
        vector_bytes = total_chunks * self.store.vector_size * 4  # float32 embeddings
        used = vector_bytes + text_bytes + repo_bytes
        try:
            target = self.data_dir if self.data_dir.exists() else Path.cwd()
            free = shutil.disk_usage(target).free
        except OSError:
            free = 0
        total = used + free
        return {
            "used_bytes": used,
            "vector_bytes": vector_bytes,
            "text_bytes": text_bytes,
            "repo_bytes": repo_bytes,
            "free_bytes": free,
            "total_bytes": total,
            "used_pct": round(used / total * 100, 2) if total else 0.0,
        }

    # -- Deletion ----------------------------------------------------------
    def delete(self, filename: str) -> dict:
        self.store.delete_by_filename(filename)
        self.summary_store.delete_by_filename(filename)
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
        self.summary_store.set_payload_by_filename(
            filename, {"tags": leaf_tags, "tag_paths": tag_paths}
        )
        self.audit.write("TAG_UPDATE", {"filename": filename, "tags": leaf_tags})
        return {"filename": filename, "tags": leaf_tags}

    # -- Description -------------------------------------------------------
    def update_description(self, filename: str, description: str) -> dict:
        """Set a document's description by rewriting it on every chunk."""
        if not self.store.has_document(filename):
            raise UserError(404, f"Document not found: {filename}")
        desc = (description or "").strip()
        self.store.set_payload_by_filename(filename, {"description": desc})
        self.summary_store.set_payload_by_filename(filename, {"description": desc})
        self.audit.write("DESCRIPTION_UPDATE", {"filename": filename})
        return {"filename": filename, "description": desc}

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

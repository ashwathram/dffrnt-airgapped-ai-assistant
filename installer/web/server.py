"""The control panel's HTTP server — stdlib only (http.server), bound to
127.0.0.1, serving the static UI plus a small JSON/SSE API over the same
Backend/Installer/model_store layer cli.py uses.

Why a local web server instead of a desktop toolkit: the browser is the one
GUI runtime every target already has, identical on Linux/Windows/macOS, so
the view layer needs no per-platform freezing, no Tk bundling, and no Mac
in the build loop. A displayless box works too — run `panel --no-browser`
and open the printed URL through an SSH tunnel.

Security model: management verbs can install and delete, so the server
binds to loopback ONLY and every page/API request must present a random
per-session token (minted at startup, embedded in the URL the browser is
opened with). Static assets are token-free — they contain nothing secret.

Concurrency model mirrors the old Tk dashboard's _busy flag: ONE mutating
job at a time (409 while busy). Job output is buffered with full history
(process.BackgroundJob + a replay list), so the SSE stream survives a page
reload mid-job. Log-follow streams are separate, read-only, and per-client.
"""

from __future__ import annotations

import hmac
import json
import secrets
import sys
import threading
import time
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .. import model_store
from ..backends import BackendError, make_backend
from ..config import find_app_root, find_config, load_config, write_config_value
from ..installers import InstallError, find_bundles, make_installer
from ..installers.docker_installer import default_install_dest, is_installed
from ..logging_setup import configure_logging, get_logger
from ..platform_detect import detect
from ..process import BackgroundJob

STATIC_DIR = Path(__file__).resolve().parent / "static"
ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"

_MIME = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
         ".js": "text/javascript; charset=utf-8", ".png": "image/png",
         ".svg": "image/svg+xml"}


class Context:
    """App root + config + backend, rebuilt on demand — the server-side
    twin of cli._Context. Mutated by install (re-point) and model_use
    (config rewrite), guarded by `lock` because handler threads share it."""

    def __init__(self):
        self.lock = threading.RLock()
        self.platform_info = detect()
        self.app_root = find_app_root()
        configure_logging(self.app_root)
        self.reload()

    def reload(self) -> None:
        with self.lock:
            self.config = load_config(self.app_root)
            self.backend = make_backend(self.app_root, self.config, self.platform_info)
            self.installer = make_installer(self.platform_info)

    def repoint(self, app_root: Path) -> None:
        with self.lock:
            self.app_root = app_root
            self.reload()


class Job:
    """One mutating operation: a BackgroundJob plus a full line history so
    a late/reconnecting SSE client replays everything already emitted."""

    def __init__(self, label: str, fn):
        self.label = label
        self.history: list[str] = []
        self._lock = threading.Lock()
        self._bg = BackgroundJob(fn)

    def start(self) -> "Job":
        self._bg.start()
        return self

    def snapshot(self, cursor: int) -> tuple[list[str], int, bool, str | None]:
        """Lines after `cursor`, the new cursor, done?, error message.
        The done flag is read BEFORE draining: the worker sets it only
        after its final queue put, so a pre-drain done means the drain
        that follows captured every line — no lost tail."""
        with self._lock:
            done = self._bg.done.is_set()
            self.history.extend(self._bg.drain())
            lines = self.history[cursor:]
            error = str(self._bg.error) if self._bg.error is not None else None
            return lines, len(self.history), done, error


class PanelServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, addr, ctx: Context, token: str):
        super().__init__(addr, Handler)
        self.ctx = ctx
        self.token = token
        self.job: Job | None = None
        self.job_lock = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    server: PanelServer  # type: ignore[assignment]
    protocol_version = "HTTP/1.1"

    # ---- plumbing ---------------------------------------------------------
    def log_message(self, fmt, *args):  # route http.server chatter to the log file
        get_logger().debug("http: " + fmt, *args)

    def _authed(self) -> bool:
        supplied = self.headers.get("X-DFFRNT-Token", "")
        if not supplied:
            supplied = parse_qs(urlparse(self.path).query).get("token", [""])[0]
        return hmac.compare_digest(supplied, self.server.token)

    def _json(self, payload, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path: Path) -> None:
        if not path.is_file():
            self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", _MIME.get(path.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _sse_start(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()

    def _sse(self, data: dict, event: str | None = None) -> None:
        msg = (f"event: {event}\n" if event else "") + f"data: {json.dumps(data)}\n\n"
        self.wfile.write(msg.encode("utf-8"))
        self.wfile.flush()

    # ---- GET --------------------------------------------------------------
    def do_GET(self):  # noqa: N802 (http.server API)
        path = urlparse(self.path).path
        if path.startswith("/assets/"):
            name = Path(path).name  # flat namespace: no traversal possible
            root = ASSETS_DIR if name == "icon.png" else STATIC_DIR
            return self._file(root / name)
        if path == "/favicon.ico" or path == "/favicon.png":
            return self._file(ASSETS_DIR / "icon.png")
        if not self._authed():
            return self._json({"error": "missing or bad token — relaunch the manager "
                                        "and use the URL it prints"}, HTTPStatus.FORBIDDEN)
        if path == "/":
            return self._file(STATIC_DIR / "index.html")
        if path == "/api/state":
            return self._state()
        if path == "/api/prereqs":
            return self._prereqs()
        if path == "/api/status":
            return self._status()
        if path == "/api/models":
            return self._models()
        if path == "/api/job/events":
            return self._job_events()
        if path == "/api/logs/events":
            return self._log_events()
        self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def _state(self) -> None:
        ctx = self.server.ctx
        with ctx.lock:
            pi, cfg = ctx.platform_info, ctx.config
            bundles = find_bundles([ctx.app_root, ctx.app_root.parent,
                                    ctx.app_root.parent / "dist", Path.cwd(),
                                    Path.cwd() / "dist"])
            self._json({
                "platform": {"os": pi.os.value, "arch": pi.arch,
                             "pathway": pi.pathway.value,
                             "gpu_detected": pi.has_nvidia_gpu,
                             "docker_present": pi.docker_present},
                "app_root": str(ctx.app_root),
                "installed": is_installed(ctx.app_root),
                "target_system": getattr(ctx.backend, "target_system", "online"),
                "config": {"api_port": cfg.api_port, "ollama_port": cfg.ollama_port,
                           "qdrant_port": cfg.qdrant_port, "gpu": cfg.gpu,
                           "llm_model": cfg.llm_model, "embed_model": cfg.embed_model},
                "bundles": [str(b) for b in bundles],
                "default_dest": str(default_install_dest()),
                "busy": self._busy(),
                "job_label": self.server.job.label if self.server.job else None,
            })

    def _prereqs(self) -> None:
        ctx = self.server.ctx
        with ctx.lock:
            try:
                install_checks = ctx.installer.check_prerequisites()
            except Exception as exc:
                install_checks = []
                get_logger().warning("install prereqs failed: %s", exc)
            try:
                manage_checks = ctx.backend.check_prerequisites()
            except Exception as exc:
                manage_checks = []
                get_logger().warning("manage prereqs failed: %s", exc)
        as_json = lambda cs: [{"name": c.name, "ok": c.ok, "detail": c.detail} for c in cs]
        self._json({"install": as_json(install_checks), "manage": as_json(manage_checks)})

    def _status(self) -> None:
        ctx = self.server.ctx
        try:
            with ctx.lock:
                services = [{"name": s.name, "running": s.running,
                             "healthy": s.healthy, "detail": s.detail}
                            for s in ctx.backend.status()]
        except Exception as exc:
            return self._json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
        self._json({"services": services})

    def _models(self) -> None:
        ctx = self.server.ctx
        with ctx.lock:
            cfg = ctx.config
            try:
                infos = ctx.backend.list_models()
            except Exception:
                infos = []
            llm = model_store.with_tag(cfg.llm_model) if cfg.llm_model else ""
            embed = model_store.with_tag(cfg.embed_model) if cfg.embed_model else ""
            kept = {model_store.with_tag(n)
                    for n in model_store.read_keep_file(ctx.app_root)}
            models = []
            for info in infos:
                role = ("llm" if info.name == llm else
                        "embedder" if info.name == embed else
                        "imported" if info.name in kept else "prunable")
                models.append({"name": info.name, "size": info.size_bytes,
                               "size_h": model_store.human_size(info.size_bytes),
                               "role": role,
                               "embedder_like": model_store.looks_like_embedder(info.name)})
            self._json({"models": models, "llm_model": cfg.llm_model,
                        "embed_model": cfg.embed_model,
                        "offline": getattr(ctx.backend, "target_system", "online") == "offline"})

    def _job_events(self) -> None:
        job = self.server.job
        self._sse_start()
        if job is None:
            return self._sse({"error": None, "label": None}, event="done")
        cursor = 0
        try:
            self._sse({"label": job.label}, event="label")
            while True:
                lines, cursor, done, error = job.snapshot(cursor)
                for line in lines:
                    self._sse({"line": line})
                if done:
                    return self._sse({"error": error, "label": job.label}, event="done")
                time.sleep(0.15)
        except (BrokenPipeError, ConnectionResetError):
            return  # client went away; the job itself keeps running

    def _log_events(self) -> None:
        service = parse_qs(urlparse(self.path).query).get("service", [None])[0]
        if service in ("all", ""):
            service = None
        ctx = self.server.ctx
        try:
            with ctx.lock:
                follower = ctx.backend.stream_logs(service, lambda _l: None)
        except Exception as exc:
            return self._json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)
        self._sse_start()
        try:
            while True:
                lines, ended = follower.drain()
                for line in lines:
                    self._sse({"line": line})
                if ended:
                    return self._sse({}, event="done")
                time.sleep(0.15)
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            follower.stop()

    # ---- POST (mutating verbs) --------------------------------------------
    def do_POST(self):  # noqa: N802
        if not self._authed():
            return self._json({"error": "bad token"}, HTTPStatus.FORBIDDEN)
        if urlparse(self.path).path != "/api/action":
            return self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return self._json({"error": "bad JSON"}, HTTPStatus.BAD_REQUEST)
        verb = payload.get("verb", "")
        try:
            self._dispatch(verb, payload)
        except (BackendError, InstallError, model_store.ModelStoreError) as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def _busy(self) -> bool:
        job = self.server.job
        if job is None:
            return False
        _, _, done, _ = job.snapshot(0)
        return not done

    def _launch(self, label: str, fn) -> None:
        """Start `fn(on_output)` as THE active job (single-flight)."""
        with self.server.job_lock:
            if self._busy():
                return self._json({"error": f"busy: {self.server.job.label} is still "
                                            "running"}, HTTPStatus.CONFLICT)
            self.server.job = Job(label, fn).start()
        self._json({"ok": True, "label": label})

    def _dispatch(self, verb: str, p: dict) -> None:
        ctx = self.server.ctx
        backend = ctx.backend

        simple = {"start": "start", "stop": "stop", "restart": "restart",
                  "dev": "start_dev", "reingest_preview": "reingest_preview",
                  "reingest_apply": "reingest_apply"}
        if verb in simple:
            return self._launch(verb.replace("_", " "), getattr(backend, simple[verb]))

        if verb == "install":
            bundle = Path(p.get("bundle", ""))
            dest = Path(p.get("dest") or default_install_dest())
            keep_config = not p.get("overwrite_config", False)
            ctx.installer.inspect_bundle(bundle)  # raises InstallError early

            def run(out):
                ctx.installer.install(bundle, dest, out, keep_config=keep_config)
                ctx.repoint(dest)  # worker thread is fine — no UI toolkit anymore
                out(f">> Manager re-pointed at {dest}")
            return self._launch(f"install {bundle.name}", run)

        if verb == "model_use":
            name = p.get("name", "").strip()
            model_store.name_to_manifest_rel(name)  # syntax check; raises
            config_path = find_config(ctx.app_root)
            if config_path is None:
                raise BackendError(f"no config.toml under {ctx.app_root} — is the stack installed?")
            offline = getattr(backend, "target_system", "online") == "offline"
            present = model_store.model_present(backend.models_dir, name)
            if offline and not present:
                raise BackendError(f"'{name}' is not in this machine's store, and an "
                                   "offline deployment cannot pull — import it first.")
            with ctx.lock:
                write_config_value(config_path, "llm_model", name)
                model_store.remove_from_keep_file(ctx.app_root, name)
                ctx.reload()
            return self._launch(f"switch model -> {name}", ctx.backend.restart)

        if verb == "model_delete":
            name = p.get("name", "").strip()
            active = {model_store.with_tag(m) for m in
                      (ctx.config.llm_model, ctx.config.embed_model) if m}
            if model_store.with_tag(name) in active:
                raise BackendError(f"{name} is the active LLM or embedder — switch first.")
            return self._launch(f"delete {name}",
                                lambda out: backend.delete_model(out, name))

        if verb == "model_import":
            tar_path = Path(p.get("path", ""))
            return self._launch(f"import {tar_path.name}",
                                lambda out: backend.import_model_tar(out, tar_path))

        if verb == "model_export":
            name = p.get("name", "").strip()
            dest = Path(p.get("dest", ""))
            if not name or not p.get("dest"):
                raise BackendError("export needs a model name and a destination path")
            model_store.name_to_manifest_rel(name)
            return self._launch(f"export {name}",
                                lambda out: backend.export_model(out, name, dest))

        self._json({"error": f"unknown verb '{verb}'"}, HTTPStatus.BAD_REQUEST)


# ---- entry ------------------------------------------------------------------

def serve(open_browser: bool = True, port: int | None = None) -> None:
    """Start the panel on 127.0.0.1 and (optionally) open the browser at the
    tokened URL. Blocks until Ctrl-C. Port: explicit arg beats
    DFFRNT_PANEL_PORT beats the 8901 default, falling back to an ephemeral
    port when the preferred one is taken."""
    import os
    ctx = Context()
    token = secrets.token_urlsafe(24)
    preferred = port if port is not None else int(os.environ.get("DFFRNT_PANEL_PORT", "8901"))
    try:
        server = PanelServer(("127.0.0.1", preferred), ctx, token)
    except OSError:
        server = PanelServer(("127.0.0.1", 0), ctx, token)
    url = f"http://127.0.0.1:{server.server_address[1]}/?token={token}"
    get_logger().info("panel serving at %s", url)
    print(f">> DFFRNT control panel: {url}", flush=True)
    print("   (Ctrl-C stops the panel; the stack itself keeps running)", flush=True)
    if open_browser:
        threading.Timer(0.3, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n>> Panel stopped.", file=sys.stderr)
    finally:
        server.server_close()

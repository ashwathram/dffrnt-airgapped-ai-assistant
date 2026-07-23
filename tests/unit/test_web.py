"""installer/web/server.py over real HTTP: token gating, the JSON API
against a stub backend, the single-flight job lock, and SSE streaming with
history replay. No docker, no browser — urllib against a PanelServer on an
ephemeral port.
"""

import json
import threading
import time
import types
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from installer.backends import BackendError, PrereqCheck, ServiceStatus
from installer.model_store import ModelInfo
from installer.web.server import PanelServer

TOKEN = "test-token"


# ---- stubs ------------------------------------------------------------------

class FakeBackend:
    def __init__(self, models_dir: Path):
        self.target_system = "offline"
        self.models_dir = models_dir
        self.release = threading.Event()
        self.release.set()  # tests that need a held-open job clear this

    def check_prerequisites(self):
        return [PrereqCheck("Docker installed", True, "ok")]

    def status(self):
        return [ServiceStatus("Qdrant", running=True, healthy=True, detail="healthy"),
                ServiceStatus("API", running=False, healthy=None, detail="not running")]

    def list_models(self):
        return [ModelInfo(name="qwen3:14b", size_bytes=9_000_000_000),
                ModelInfo(name="bge-m3:latest", size_bytes=1_100_000_000)]

    def start(self, on_output):
        on_output(">> starting")
        self.release.wait(timeout=5)
        on_output(">> started")

    def stop(self, on_output):
        raise BackendError("stop exploded")

    def restart(self, on_output):
        # Exists on every real Backend (ABC default); the busy test resolves
        # it but must never run it — the 409 fires first.
        raise AssertionError("restart ran despite an active job")


class FakeContext:
    def __init__(self, app_root: Path):
        self.lock = threading.RLock()
        self.app_root = app_root
        self.platform_info = types.SimpleNamespace(
            os=types.SimpleNamespace(value="linux"), arch="x86_64",
            pathway=types.SimpleNamespace(value="container"),
            has_nvidia_gpu=False, docker_present=True)
        self.config = types.SimpleNamespace(
            api_port=8000, ollama_port="11434", qdrant_port="6333", gpu=False,
            llm_model="qwen3:14b", embed_model="bge-m3")
        self.backend = FakeBackend(app_root / "ollama_models")
        self.installer = types.SimpleNamespace(check_prerequisites=lambda: [])

    def reload(self):
        pass


@pytest.fixture()
def panel(tmp_path):
    (tmp_path / "config.toml").write_text('llm_model = "qwen3:14b"\n')
    ctx = FakeContext(tmp_path)
    server = PanelServer(("127.0.0.1", 0), ctx, TOKEN)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    yield base, ctx
    server.shutdown()
    server.server_close()


def _get(base, path, token=TOKEN, raw=False):
    req = urllib.request.Request(base + path,
                                 headers={"X-DFFRNT-Token": token} if token else {})
    with urllib.request.urlopen(req, timeout=5) as res:
        body = res.read()
        return body if raw else json.loads(body)


def _post(base, payload, token=TOKEN):
    req = urllib.request.Request(
        base + "/api/action", data=json.dumps(payload).encode(),
        headers={"X-DFFRNT-Token": token, "Content-Type": "application/json"},
        method="POST")
    with urllib.request.urlopen(req, timeout=5) as res:
        return res.status, json.loads(res.read())


def _sse_lines(base, path, timeout=5.0):
    """Collect SSE data payloads until the done event (or timeout)."""
    req = urllib.request.Request(base + path + f"?token={TOKEN}")
    lines, done_payload = [], None
    deadline = time.time() + timeout
    with urllib.request.urlopen(req, timeout=timeout) as res:
        event = None
        while time.time() < deadline:
            raw = res.readline().decode().strip()
            if raw.startswith("event: "):
                event = raw[7:]
            elif raw.startswith("data: "):
                payload = json.loads(raw[6:])
                if event == "done":
                    done_payload = payload
                    break
                if "line" in payload:
                    lines.append(payload["line"])
                event = None
    return lines, done_payload


# ---- auth -------------------------------------------------------------------

def test_token_required(panel):
    base, _ = panel
    with pytest.raises(urllib.error.HTTPError) as exc:
        _get(base, "/api/state", token=None)
    assert exc.value.code == 403
    with pytest.raises(urllib.error.HTTPError) as exc:
        _get(base, "/", token="wrong")
    assert exc.value.code == 403


def test_assets_are_open_but_flat(panel):
    base, _ = panel
    body = _get(base, "/assets/style.css", token=None, raw=True)
    assert b"--sidebar" in body
    # Traversal collapses to the basename — never escapes the static dir.
    with pytest.raises(urllib.error.HTTPError) as exc:
        _get(base, "/assets/..%2F..%2Fconfig.py", token=None)
    assert exc.value.code == 404


# ---- read API ---------------------------------------------------------------

def test_state_status_models(panel):
    base, ctx = panel
    state = _get(base, "/api/state")
    assert state["platform"]["pathway"] == "container"
    assert state["target_system"] == "offline"
    assert state["config"]["llm_model"] == "qwen3:14b"
    assert state["busy"] is False

    status = _get(base, "/api/status")
    assert [s["name"] for s in status["services"]] == ["Qdrant", "API"]

    models = _get(base, "/api/models")
    roles = {m["name"]: m["role"] for m in models["models"]}
    assert roles == {"qwen3:14b": "llm", "bge-m3:latest": "embedder"}
    assert models["offline"] is True


# ---- jobs: run, stream, single-flight, error surfacing ----------------------

def test_job_stream_and_busy_conflict(panel):
    base, ctx = panel
    ctx.backend.release.clear()  # hold the job open
    status, body = _post(base, {"verb": "start"})
    assert status == 200 and body["ok"]

    # Single-flight: a second action while running is refused.
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post(base, {"verb": "restart"})
    assert exc.value.code == 409

    assert _get(base, "/api/state")["busy"] is True
    ctx.backend.release.set()

    lines, done = _sse_lines(base, "/api/job/events")
    assert lines == [">> starting", ">> started"]
    assert done["error"] is None

    # History replay: a second (late) client sees the full transcript.
    lines2, done2 = _sse_lines(base, "/api/job/events")
    assert lines2 == [">> starting", ">> started"] and done2["error"] is None


def test_job_error_surfaces_in_done_event(panel):
    base, _ = panel
    status, _ = _post(base, {"verb": "stop"})
    assert status == 200
    _, done = _sse_lines(base, "/api/job/events")
    assert "stop exploded" in done["error"]


# ---- verb validation --------------------------------------------------------

def test_bad_verbs_and_offline_model_use(panel):
    base, _ = panel
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post(base, {"verb": "frobnicate"})
    assert exc.value.code == 400
    # Offline + model not in (empty) store -> refused before any config write.
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post(base, {"verb": "model_use", "name": "qwen3:8b"})
    assert exc.value.code == 400
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post(base, {"verb": "model_export", "name": "qwen3:14b"})  # no dest
    assert exc.value.code == 400

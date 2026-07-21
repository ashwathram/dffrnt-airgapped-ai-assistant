"""PORTABLE pathway (macOS) — NOT IMPLEMENTED YET.

Why macOS needs a different pathway at all: Docker Desktop on macOS runs
containers inside a Linux VM, and that VM has no Metal/GPU passthrough. A
containerized Ollama on a Mac is therefore CPU-only regardless of the
host's Apple Silicon GPU — unacceptable for the LLM/embedding workload
this app depends on.

The planned fix carries two portable, self-contained artifacts in the
macOS-specific dist bundle instead of relying on docker-compose.yml
directly:

  - Ollama runs as a native host *process* (a vendored, portable Ollama
    binary — not the containerized image the Linux/Windows pathway uses),
    so it gets full Metal acceleration.
  - Qdrant, which is CPU-only and not GPU-sensitive, still runs via a
    bundled portable container runtime — vendored alongside Ollama in the
    same dist bundle rather than assuming Docker Desktop is preinstalled,
    since the container pathway can't assume that on macOS the way it can
    lean on a prerequisite step on Linux.

None of that is built yet. This class exists so platform_detect.Pathway
routing and the Backend interface are already shaped to receive it:
whoever implements this later fills in these methods without touching
platform_detect.py, the Backend ABC, or any view.

Expected layout once implemented (not yet created):
    installer/vendor/macos/ollama          # portable Ollama binary
    installer/vendor/macos/<container rt>  # portable Qdrant runtime
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from ..config import AppConfig
from ..logging_setup import get_logger
from . import Backend, OutputCallback, PrereqCheck, ServiceStatus

_NOT_IMPLEMENTED = (
    "The macOS pathway (native Ollama + portable Qdrant runtime) isn't "
    "implemented yet. See installer/backends/portable_backend.py."
)


def _unavailable(stage: str) -> None:
    # Every attempted operation is logged even though none of them work
    # yet, so "a macOS user tried to start the stack" leaves a trace once
    # this phase actually ships to a Mac.
    get_logger().warning("%s: unavailable — %s", stage, _NOT_IMPLEMENTED)
    raise NotImplementedError(_NOT_IMPLEMENTED)


class PortableBackend(Backend):
    def __init__(self, app_root: Path, config: AppConfig):
        self.app_root = app_root
        self.config = config

    def check_prerequisites(self) -> list[PrereqCheck]:
        get_logger().warning("check_prerequisites: %s", _NOT_IMPLEMENTED)
        return [PrereqCheck("macOS pathway implemented", False, _NOT_IMPLEMENTED)]

    def start(self, on_output: OutputCallback) -> None:
        _unavailable("start")

    def stop(self, on_output: OutputCallback) -> None:
        _unavailable("stop")

    def status(self) -> Iterable[ServiceStatus]:
        return [ServiceStatus("macOS pathway", running=False, healthy=None, detail=_NOT_IMPLEMENTED)]

    def stream_logs(self, service: str | None, on_line: OutputCallback):
        _unavailable("stream_logs")

    def reingest_preview(self, on_output: OutputCallback) -> None:
        _unavailable("reingest.preview")

    def reingest_apply(self, on_output: OutputCallback) -> None:
        _unavailable("reingest.apply")

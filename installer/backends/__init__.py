"""The Backend interface every pathway implements.

The GUI (views/) talks only to this interface, never to `docker compose` or
a native process directly — that's what lets the same Dashboard/Logs views
work against DockerComposeBackend (Linux/Windows, implemented) and, later,
PortableBackend (macOS, stubbed) without an if/else on OS anywhere in the
UI layer. See platform_detect.py for how a PlatformInfo picks a backend.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Iterable

OutputCallback = Callable[[str], None]


@dataclass(frozen=True)
class PrereqCheck:
    name: str
    ok: bool
    detail: str = ""


@dataclass(frozen=True)
class ServiceStatus:
    name: str
    running: bool
    healthy: bool | None  # None = unknown/not applicable
    detail: str = ""


class BackendError(RuntimeError):
    """Raised for expected failures (docker not running, compose missing,
    ...) so the GUI can show a message instead of a traceback."""


class Backend(ABC):
    """Verbs mirror deploy/dffrnt_ctrl_panel.sh's command set: start, stop,
    restart, status, logs, reingest — plus check_prerequisites, which
    mirrors install.sh's prerequisite gate.

    All long-running methods stream progress via an OutputCallback rather
    than returning captured text, so the GUI can pipe it straight into a
    live console. Callbacks may be invoked from a background thread —
    callers marshal back onto the Tk main thread (see process.py).
    """

    @abstractmethod
    def check_prerequisites(self) -> list[PrereqCheck]:
        """Non-mutating. What's missing before start() can work."""

    @abstractmethod
    def start(self, on_output: OutputCallback) -> None:
        ...

    @abstractmethod
    def stop(self, on_output: OutputCallback) -> None:
        ...

    def restart(self, on_output: OutputCallback) -> None:
        self.stop(on_output)
        self.start(on_output)

    @abstractmethod
    def status(self) -> Iterable[ServiceStatus]:
        """Non-mutating snapshot; safe to poll."""

    @abstractmethod
    def stream_logs(self, service: str | None, on_line: OutputCallback):
        """Start following logs (all services if service is None). Returns
        a handle with a `.stop()` method the caller uses to end the follow.
        """

    def reingest_preview(self, on_output: OutputCallback) -> None:
        """Dry run: lists what a force reingest would touch. Never mutates
        anything — safe to call without confirmation."""
        raise NotImplementedError("reingest is not implemented for this pathway yet.")

    def reingest_apply(self, on_output: OutputCallback) -> None:
        """Force re-ingest every stored document. Mutating — callers should
        only invoke this after showing the operator reingest_preview's
        output and getting explicit confirmation (see views/dashboard.py)."""
        raise NotImplementedError("reingest is not implemented for this pathway yet.")

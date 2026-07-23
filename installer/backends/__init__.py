"""The Backend interface every pathway implements.

The UI layers (views/ for the GUI, cli.py for headless targets) talk only
to this interface, never to `docker compose` or a native process directly —
that's what lets the same surfaces work against DockerComposeBackend
(Linux/Windows) and PortableBackend (macOS) without an if/else on OS
anywhere above. See platform_detect.py for how a PlatformInfo picks a
backend, and make_backend below for the single place that choice is made.
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
    """The management verb set: start, stop, restart, status, logs,
    reingest, the model-store operations, and check_prerequisites (the
    pre-start gate). This is the reference implementation of stack
    management — the retired deploy shell scripts (dffrnt_ctrl_panel.sh,
    install.sh) were its ancestors, and their behavior contracts (GPU
    override, model ensure/prune, health-wait order) live on here.

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

    # ---- model store operations (views/models.py) -------------------------
    # All host-side against the ollama_models directory, so they work with
    # the stack down — except pull/delete, which talk to the serving Ollama.

    def list_models(self):
        """Non-mutating: every model in the store as model_store.ModelInfo,
        across all registry namespaces."""
        raise NotImplementedError("model management is not implemented for this pathway yet.")

    def ollama_reachable(self) -> bool:
        """Non-mutating: is the serving Ollama up (pull/delete need it)?"""
        raise NotImplementedError("model management is not implemented for this pathway yet.")

    def pull_model(self, on_output: OutputCallback, name: str) -> None:
        """Pull ``name`` from the registry into the store (networked
        machines only — an offline bundle refuses). on_output comes first,
        matching the (self, on_output, *args) shape every mutating verb
        shares so they wrap uniformly (see docker_backend._logged)."""
        raise NotImplementedError("model management is not implemented for this pathway yet.")

    def delete_model(self, on_output: OutputCallback, name: str) -> None:
        """Remove ``name`` from the store and the keep file. Mutating and,
        on an air-gapped box, unrecoverable — confirm first."""
        raise NotImplementedError("model management is not implemented for this pathway yet.")

    def export_model(self, on_output: OutputCallback, name: str, dest_tar) -> None:
        """Pack ``name`` (manifest + blobs) into an uncompressed tar for
        USB transfer, pulling it first if absent (online machines)."""
        raise NotImplementedError("model management is not implemented for this pathway yet.")

    def import_model_tar(self, on_output: OutputCallback, tar_path) -> list[str]:
        """Merge an exported model tar into the store (checksum-verified)
        and protect the imported models from the start-time prune. Returns
        the imported model names."""
        raise NotImplementedError("model management is not implemented for this pathway yet.")

    def start_dev(self, on_output: OutputCallback) -> None:
        """Dev-loop bring-up: only the dependency services (Qdrant +
        Ollama), so the API can run on the host under a debugger. Never
        prunes models. Not meaningful on an installed target."""
        raise NotImplementedError("the dev loop is not implemented for this pathway.")


def make_backend(app_root, config, platform_info) -> "Backend":
    """The one place a PlatformInfo picks a Backend implementation, shared
    by the GUI shell (app.py) and the CLI. Imports live inside so this
    module stays import-cycle-free (concrete backends import from here)."""
    from ..platform_detect import Pathway
    from .docker_backend import DockerComposeBackend
    from .portable_backend import PortableBackend

    if platform_info.pathway is Pathway.PORTABLE:
        return PortableBackend(app_root, config)
    return DockerComposeBackend(app_root, config)

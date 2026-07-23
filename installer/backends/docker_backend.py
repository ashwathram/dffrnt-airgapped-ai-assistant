"""CONTAINER pathway (Linux/Windows): drives the `docker compose` stack.
This IS the reference implementation of stack management (it absorbed the
retired dffrnt_ctrl_panel.sh shell script verb for verb — GPU override,
model ensure/prune, health-wait order all originated there and their
behavior contracts continue here unchanged).
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Iterable

from .. import model_store, process
from ..config import AppConfig, read_bundle_conf
from ..logging_setup import get_logger, with_logging
from . import Backend, BackendError, OutputCallback, PrereqCheck, ServiceStatus

_CONTAINER_NAMES = {
    "Qdrant": "qdrant",
    "Ollama": "ollama",
    "API": "dffrnt-api",
}

# python -u -m dffrnt_assistant.ingest.backfill --force, run inside the API
# container. Safety order: dry-run preview first, force+verbose only after
# the operator confirms (dialog in the GUI, prompt in the CLI).
_REINGEST_CMD = ["python", "-u", "-m", "dffrnt_assistant.ingest.backfill", "--force"]


def _logged(stage: str):
    """Decorates a Backend(self, on_output, ...) method: logs a begin/end/
    error bracket around it and mirrors every line it emits into the log
    file via with_logging. Applied to start/stop/reingest_preview/apply —
    the "install or command management" lifecycle operations — not to
    status()/stream_logs(), which take no on_output and are the read-only
    "management" operations intentionally left out of the log file (see
    logging_setup.py's module docstring).
    """

    def decorator(fn):
        def wrapper(self, on_output: OutputCallback, *args, **kwargs):
            logger = get_logger()
            logger.info("%s: starting", stage)
            try:
                result = fn(self, with_logging(stage, on_output), *args, **kwargs)
            except Exception:
                logger.exception("%s: failed", stage)
                raise
            logger.info("%s: complete", stage)
            return result

        wrapper.__name__ = fn.__name__
        wrapper.__doc__ = fn.__doc__
        return wrapper

    return decorator


class DockerComposeBackend(Backend):
    def __init__(self, app_root: Path, config: AppConfig):
        self.app_root = app_root
        self.config = config
        self.compose_file = app_root / "docker-compose.yml"
        target_system, bundled_models = read_bundle_conf(app_root)
        self.target_system = target_system
        self.bundled_models = bundled_models

    # ---- command building / pathway seams --------------------------------
    # PortableBackend (macOS) subclasses this backend and overrides these
    # seams; keep pathway differences INSIDE them so the lifecycle flow in
    # start()/stop()/reingest stays single-sourced.

    def _env(self) -> dict | None:
        """Process environment for every docker/ollama invocation. None =
        inherit. The portable pathway injects its bundled bin dir + the
        colima DOCKER_HOST here."""
        return None

    def _ollama_cmd(self) -> list[str]:
        """How to invoke the ollama CLI against the serving instance:
        containerized here, the native host binary on macOS."""
        return ["docker", "exec", "ollama", "ollama"]

    def _compose_cmd(self, *args: str) -> list[str]:
        return [
            "docker", "compose",
            "-f", str(self.compose_file),
            "--profile", "prod",
            *args,
        ]

    # ---- Backend interface ----------------------------------------------
    def check_prerequisites(self) -> list[PrereqCheck]:
        logger = get_logger()
        logger.info("check_prerequisites: starting")
        checks = self._check_prerequisites()
        for check in checks:
            level = logging.INFO if check.ok else logging.WARNING
            logger.log(level, "check_prerequisites: %s = %s%s",
                       check.name, "ok" if check.ok else "MISSING",
                       f" ({check.detail})" if check.detail else "")
        logger.info("check_prerequisites: complete (%d/%d ok)",
                    sum(1 for c in checks if c.ok), len(checks))
        return checks

    def _check_prerequisites(self) -> list[PrereqCheck]:
        checks = []

        try:
            version = process.run_capture(["docker", "--version"])
            checks.append(PrereqCheck("Docker installed", True, version))
        except Exception:
            checks.append(PrereqCheck(
                "Docker installed", False,
                "install Docker Engine + the Compose v2 plugin",
            ))
            return checks  # nothing else below can succeed without it

        try:
            process.run_capture(["docker", "info"])
            checks.append(PrereqCheck("Docker daemon running", True))
        except Exception:
            checks.append(PrereqCheck(
                "Docker daemon running", False,
                "start Docker (e.g. `systemctl start docker`) and ensure your user can access it",
            ))

        try:
            version = process.run_capture(["docker", "compose", "version"])
            checks.append(PrereqCheck("Compose v2 plugin", True, version))
        except Exception:
            checks.append(PrereqCheck("Compose v2 plugin", False, "install the Docker Compose v2 plugin"))

        if not self.compose_file.is_file():
            checks.append(PrereqCheck(
                "docker-compose.yml found", False, f"expected at {self.compose_file}",
            ))
        else:
            checks.append(PrereqCheck("docker-compose.yml found", True, str(self.compose_file)))

        if self.config.gpu:
            try:
                info = process.run_capture(["docker", "info"])
                has_nvidia = "nvidia" in info.lower()
            except Exception:
                has_nvidia = False
            checks.append(PrereqCheck(
                "NVIDIA runtime registered with Docker", has_nvidia,
                "" if has_nvidia else (
                    "gpu = true in config.toml, but Docker has no NVIDIA runtime — "
                    "install the NVIDIA driver + Container Toolkit, or set gpu = false"
                ),
            ))

        return checks

    @_logged("start")
    def start(self, on_output: OutputCallback) -> None:
        (self.app_root / "data").mkdir(parents=True, exist_ok=True)
        (self.app_root / "logs").mkdir(parents=True, exist_ok=True)

        self._preflight(on_output)
        self._compose_up(on_output)

        self._wait_for("Qdrant", f"http://localhost:{self.config.qdrant_port}/healthz", 120, on_output)
        self._wait_for("Ollama", f"http://localhost:{self.config.ollama_port}", 120, on_output)
        self._ensure_models(on_output)
        self._prune_models(on_output)
        ready = self._wait_for("API", f"http://localhost:{self.config.api_port}/health", 120, on_output)
        if not ready:
            on_output("   (API not healthy yet — it restarts automatically; check the Logs view)")
        on_output(f">> Up. UI: http://localhost:{self.config.api_port}")

    def _preflight(self, on_output: OutputCallback) -> None:
        """Pathway-specific readiness before compose up. Container pathway:
        the NVIDIA-runtime gate for gpu = true. Portable (macOS): boot the
        bundled runtime + the native Ollama process instead."""
        if self.config.gpu:
            try:
                info = process.run_capture(["docker", "info"], env=self._env())
            except Exception as exc:
                raise BackendError(f"could not reach the Docker daemon: {exc}") from exc
            if "nvidia" not in info.lower():
                raise BackendError(
                    "gpu = true in config.toml, but Docker has no NVIDIA runtime. "
                    "Install the NVIDIA driver + Container Toolkit, or set gpu = false "
                    "to run on CPU."
                )

    def _compose_up(self, on_output: OutputCallback) -> None:
        """Bring the containers up. Portable (macOS) overrides this to start
        only qdrant + api, with the API pointed at the native Ollama."""
        ports = (f"api:{self.config.api_port} "
                 f"ollama:{self.config.ollama_port} qdrant:{self.config.qdrant_port}")
        if self.config.gpu:
            on_output(f">> GPU mode — {ports}")
            # Stdin-YAML override piped into `compose -f -`: one compose
            # file, the GPU reservation injected only when configured.
            process.run_command(
                self._compose_cmd("-f", "-", "up", "-d"),
                on_output,
                cwd=self.app_root,
                env=self._env(),
                input_text="services:\n  ollama:\n    gpus: all\n",
            )
        else:
            on_output(f">> CPU mode — {ports}")
            process.run_command(self._compose_cmd("up", "-d"), on_output,
                                cwd=self.app_root, env=self._env())

    @_logged("stop")
    def stop(self, on_output: OutputCallback) -> None:
        on_output(">> Stopping containers")
        process.run_command(self._compose_cmd("down"), on_output,
                            cwd=self.app_root, env=self._env())

    @_logged("start.dev")
    def start_dev(self, on_output: OutputCallback) -> None:
        """Dev loop (CLI `dev`): bring up ONLY qdrant + ollama, GPU-aware,
        so the API can run on the host (e.g. the VS Code debugger) against
        them. Waits for health and ensures the configured models are
        present, but never prunes — a dev store accumulating models is the
        developer's business. Container pathway only."""
        self._preflight(on_output)
        ports = f"ollama:{self.config.ollama_port} qdrant:{self.config.qdrant_port}"
        # Explicit service names keep the prod-profile api service down.
        if self.config.gpu:
            on_output(f">> GPU mode — dev services: {ports}")
            process.run_command(
                self._compose_cmd("-f", "-", "up", "-d", "qdrant", "ollama"),
                on_output, cwd=self.app_root, env=self._env(),
                input_text="services:\n  ollama:\n    gpus: all\n",
            )
        else:
            on_output(f">> CPU mode — dev services: {ports}")
            process.run_command(self._compose_cmd("up", "-d", "qdrant", "ollama"),
                                on_output, cwd=self.app_root, env=self._env())
        self._wait_for("Qdrant", f"http://localhost:{self.config.qdrant_port}/healthz", 120, on_output)
        self._wait_for("Ollama", f"http://localhost:{self.config.ollama_port}", 120, on_output)
        self._ensure_models(on_output)
        on_output(">> Dev services up. Run the API on the host (VS Code launch config).")

    @_logged("reingest.preview")
    def reingest_preview(self, on_output: OutputCallback) -> None:
        self._require_api_running()
        on_output(">> Reconciliation preview (no changes made yet):")
        process.run_command(
            ["docker", "exec", "dffrnt-api", *_REINGEST_CMD, "--dry-run"], on_output,
            env=self._env(),
        )

    @_logged("reingest.apply")
    def reingest_apply(self, on_output: OutputCallback) -> None:
        self._require_api_running()
        on_output(">> Force re-ingesting every stored document in the live API (this can take a while)…")
        process.run_command(
            ["docker", "exec", "dffrnt-api", *_REINGEST_CMD, "--verbose"], on_output,
            env=self._env(),
        )
        on_output(">> Re-ingestion complete.")

    def _require_api_running(self) -> None:
        try:
            process.run_capture(["docker", "exec", "dffrnt-api", "true"], env=self._env())
        except Exception as exc:
            raise BackendError(
                "The API container 'dffrnt-api' is not running — start the stack first."
            ) from exc

    # Deliberately not @_logged / not writing to the log file: these are
    # read-only "management" polling, not operations. status() is re-run
    # after every action and on a timer; stream_logs()'s output is Docker's
    # own container logs, already persisted by Docker. See
    # logging_setup.py's module docstring for the reasoning.
    def status(self) -> Iterable[ServiceStatus]:
        results = []
        for label, container in _CONTAINER_NAMES.items():
            results.append(self._inspect(label, container))
        return results

    def stream_logs(self, service: str | None, on_line: OutputCallback):
        cmd = self._compose_cmd("logs", "-f", "--tail", "200", *([service] if service else []))
        return process.LogFollower(cmd, cwd=self.app_root, env=self._env())

    # ---- lifecycle helpers (health waits, model ensure/prune) ------------
    def _wait_for(self, label: str, url: str, max_seconds: int, on_output: OutputCallback) -> bool:
        on_output(f">> Waiting for {label}")
        for _ in range(max_seconds):
            if process.probe_http(url):
                on_output(f">> {label} ready")
                return True
            time.sleep(1)
        on_output(f">> {label} timeout")
        return False

    def _cached_models(self) -> set[str]:
        try:
            out = process.run_capture([*self._ollama_cmd(), "list"], env=self._env())
        except Exception:
            return set()
        lines = out.splitlines()[1:]  # drop the header row
        return {line.split()[0] for line in lines if line.split()}

    @staticmethod
    def _with_tag(name: str) -> str:
        return name if ":" in name else f"{name}:latest"

    def _wanted_models(self) -> list[str]:
        # Union of what package.sh froze into the bundle and whatever the
        # live config.toml points at now — both matter: editing the model +
        # restart mustn't run against a model Ollama never pulled.
        wanted, seen = [], set()
        for name in [*self.bundled_models, self.config.llm_model, self.config.embed_model]:
            if not name or name in seen:
                continue
            seen.add(name)
            wanted.append(name)
        return wanted

    def _ensure_models(self, on_output: OutputCallback) -> None:
        wanted = self._wanted_models()
        if not wanted:
            return
        cached = self._cached_models()
        for name in wanted:
            want = self._with_tag(name)
            if want in cached:
                continue
            if self.target_system == "offline":
                on_output(f"!! Model '{name}' missing from the cached store")
            else:
                on_output(f">> Pulling model: {name} (not in local cache)")
                process.run_command([*self._ollama_cmd(), "pull", name], on_output, env=self._env())

    def _manifest_model_names(self) -> list[str]:
        """Every model named by a manifest file in the store, including ones
        `ollama list` hides because their manifest is broken. The store is a
        host directory on every pathway (bind-mounted into the container on
        Linux/Windows, OLLAMA_MODELS for the native macOS process), so walk
        it directly — no docker exec, and it works with the stack down.
        Covers ALL registry namespaces (hf.co/... included)."""
        return [info.name for info in model_store.list_models(self.models_dir)]

    def _prune_models(self, on_output: OutputCallback) -> None:
        keep = {self._with_tag(m) for m in (self.config.llm_model, self.config.embed_model) if m}
        if not keep:
            return
        # Never sweep a model the operator imported over USB but hasn't
        # switched to yet — on an air-gapped box that deletion costs another
        # physical media trip. See model_store's keep-file comment.
        keep |= {self._with_tag(m) for m in model_store.read_keep_file(self.app_root)}
        for name in self._cached_models():
            if name not in keep:
                on_output(f">> Removing cached model no longer in use: {name}")
                process.run_command([*self._ollama_cmd(), "rm", name], on_output,
                                    check=False, env=self._env())
        # `ollama list` hides models with a broken manifest, so sweep the
        # manifest files directly too — otherwise a half-broken model leaks
        # disk forever and spams the Ollama log on every list request.
        for full in self._manifest_model_names():
            if full not in keep:
                on_output(f">> Removing stale model manifest: {full}")
                process.run_command([*self._ollama_cmd(), "rm", full], on_output,
                                    check=False, env=self._env())

    # ---- model store operations (Backend interface; views/models.py) ------
    # Pathway-independent: the store is a host directory everywhere (see
    # _manifest_model_names), and pull/delete go through the _ollama_cmd
    # seam, so PortableBackend inherits all of these unchanged.

    @property
    def models_dir(self) -> Path:
        return self.app_root / "ollama_models"

    def list_models(self) -> list[model_store.ModelInfo]:
        return model_store.list_models(self.models_dir)

    def ollama_reachable(self) -> bool:
        return process.probe_http(f"http://localhost:{self.config.ollama_port}")

    @_logged("model.pull")
    def pull_model(self, on_output: OutputCallback, name: str) -> None:
        if self.target_system == "offline":
            raise BackendError(
                "This is an offline (air-gapped) deployment — models cannot be "
                "pulled here. Export a tarball on a networked machine and use "
                "Import instead.")
        if not self.ollama_reachable():
            raise BackendError(
                "Ollama is not running — start the stack (Manage tab) first, "
                "then pull.")
        on_output(f">> Pulling model: {name}")
        process.run_command([*self._ollama_cmd(), "pull", name], on_output, env=self._env())

    @_logged("model.delete")
    def delete_model(self, on_output: OutputCallback, name: str) -> None:
        # `ollama rm` (not a manual manifest delete) so shared blobs are
        # reference-counted correctly — it needs the server up.
        if not self.ollama_reachable():
            raise BackendError(
                "Ollama is not running — start the stack (Manage tab) first, "
                "then delete.")
        on_output(f">> Removing model: {name}")
        process.run_command([*self._ollama_cmd(), "rm", name], on_output, env=self._env())
        model_store.remove_from_keep_file(self.app_root, name)

    @_logged("model.export")
    def export_model(self, on_output: OutputCallback, name: str, dest_tar: Path) -> None:
        if not model_store.model_present(self.models_dir, name):
            self.pull_model(on_output, name)
        try:
            model_store.export_model(self.models_dir, name, dest_tar, on_output)
        except model_store.ModelStoreError as exc:
            raise BackendError(str(exc)) from exc

    @_logged("model.import")
    def import_model_tar(self, on_output: OutputCallback, tar_path: Path) -> list[str]:
        try:
            names = model_store.import_tarball(tar_path, self.models_dir, on_output)
        except model_store.ModelStoreError as exc:
            raise BackendError(str(exc)) from exc
        model_store.add_to_keep_file(self.app_root, names)
        on_output(">> Protected from the start-time prune (models.keep) until "
                  "selected as the active model.")
        return names

    def _inspect(self, label: str, container: str) -> ServiceStatus:
        try:
            raw = process.run_capture(["docker", "inspect", "--format", "{{json .State}}", container],
                                      env=self._env())
            state = json.loads(raw)
        except Exception:
            # Covers both "container doesn't exist" (nonzero exit) and any
            # unparseable output — status() must degrade, never crash.
            return ServiceStatus(label, running=False, healthy=None, detail="not running")
        running = bool(state.get("Running"))
        health = (state.get("Health") or {}).get("Status")
        healthy = {"healthy": True, "unhealthy": False}.get(health)
        detail = health or ("running" if running else "stopped")
        if label == "API" and running and healthy is None:
            # The API container has no compose-level healthcheck; probe its
            # /health endpoint directly.
            ok = process.probe_http(f"http://localhost:{self.config.api_port}/health")
            healthy = ok
            detail = "healthy" if ok else "starting"
        return ServiceStatus(label, running=running, healthy=healthy, detail=detail)

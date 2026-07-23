"""PORTABLE pathway (macOS): native Ollama with Metal + containers in a
bundled portable runtime.

Why macOS can't use the container pathway: Docker's Linux VM has no
Metal/GPU passthrough, so a containerized Ollama on a Mac is CPU-only
regardless of the host's Apple Silicon GPU. Instead:

  - **Ollama runs as a native host process** from the vendored binary in
    the bundle (portable/bin/ollama). On Apple Silicon the native binary
    uses Metal automatically — no flag exists or is needed; keeping it OUT
    of the VM is the entirety of "enabling Metal". Its model store is the
    same ./ollama_models directory the bundle ships (OLLAMA_MODELS), and it
    gets the same tuning env the compose service sets (KEEP_ALIVE,
    FLASH_ATTENTION, KV_CACHE_TYPE, ...) so performance behavior matches
    the Linux deployment.

  - **Qdrant + the API run as containers** under colima (Apple's
    Virtualization.framework via lima) using the bundled static docker CLI
    + compose plugin — all vendored in portable/bin by the packaging step
    (deploy/package-macos-portable.sh), nothing installed system-wide.
    State is contained too: COLIMA_HOME/LIMA_HOME/DOCKER_CONFIG all live
    under portable/, so deleting the app root removes everything.

  - The API container reaches the host's Ollama via host.docker.internal
    (mapped with extra_hosts: host-gateway), so the native process must
    listen on 0.0.0.0 — acceptable on an air-gapped box, and required
    because the VM cannot reach the host's 127.0.0.1 under every colima
    network mode.

This subclasses DockerComposeBackend and overrides its pathway seams
(_env/_ollama_cmd/_preflight/_compose_up) plus the Ollama-specific
status/log handling; the lifecycle flow, model ensure/prune/store
operations, health waits, and reingest are inherited unchanged.
"""

from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path
from typing import Iterable

from .. import process
from ..config import AppConfig
from ..logging_setup import get_logger
from . import BackendError, OutputCallback, PrereqCheck, ServiceStatus
from .docker_backend import DockerComposeBackend, _logged

# Parity with the ollama service's environment in deploy/docker-compose.yml —
# see the comments there for what each knob does and why.
_OLLAMA_TUNING = {
    "OLLAMA_KEEP_ALIVE": "-1",
    "OLLAMA_MAX_LOADED_MODELS": "2",
    "OLLAMA_NUM_PARALLEL": "1",
    "OLLAMA_FLASH_ATTENTION": "1",
    "OLLAMA_KV_CACHE_TYPE": "q8_0",
}

_RUNTIME_BINS = ("ollama", "docker", "colima", "limactl")


class PortableBackend(DockerComposeBackend):
    def __init__(self, app_root: Path, config: AppConfig):
        super().__init__(app_root, config)
        self.portable_dir = app_root / "portable"
        self.bin_dir = self.portable_dir / "bin"
        self._ollama_log = app_root / "logs" / "ollama-native.log"
        self._ollama_pidfile = app_root / "logs" / "ollama-native.pid"

    # ---- pathway seams (see DockerComposeBackend) -------------------------
    def _env(self) -> dict:
        env = dict(os.environ)
        env["PATH"] = f"{self.bin_dir}{os.pathsep}{env.get('PATH', '')}"
        # Contain ALL runtime state under portable/ instead of $HOME, so an
        # install is self-delimiting and two installs can't fight over state.
        env["COLIMA_HOME"] = str(self.portable_dir / "colima")
        env["LIMA_HOME"] = str(self.portable_dir / "lima")
        env["DOCKER_CONFIG"] = str(self.portable_dir / "docker-config")
        env["DOCKER_HOST"] = f"unix://{self.portable_dir / 'colima' / 'default' / 'docker.sock'}"
        # For the native ollama CLI: the bundle's model store, and where to
        # find the server. OLLAMA_HOST is dual-purpose — for the CLI it's the
        # address to CONNECT to (so 127.0.0.1 here); the serve process gets
        # its own 0.0.0.0 BIND override in _ensure_native_ollama.
        env["OLLAMA_MODELS"] = str(self.app_root / "ollama_models")
        env["OLLAMA_HOST"] = f"127.0.0.1:{self.config.ollama_port}"
        return env

    def _ollama_cmd(self) -> list[str]:
        return [str(self.bin_dir / "ollama")]

    # _manifest_model_names: inherited. The parent now walks the host-side
    # store directly (app_root/ollama_models — the same directory OLLAMA_MODELS
    # points the native process at), so the old host-walk override here became
    # the shared implementation.

    # ---- prerequisites ----------------------------------------------------
    def _check_prerequisites(self) -> list[PrereqCheck]:
        checks = []
        missing = [b for b in _RUNTIME_BINS if not (self.bin_dir / b).is_file()]
        if missing:
            checks.append(PrereqCheck(
                "Portable runtime present", False,
                f"missing {', '.join(missing)} in {self.bin_dir} — install from a "
                "macOS bundle packaged with deploy/package-macos-portable.sh",
            ))
            return checks
        checks.append(PrereqCheck("Portable runtime present", True, str(self.bin_dir)))

        import platform
        apple_silicon = platform.machine().lower() in ("arm64", "aarch64")
        checks.append(PrereqCheck(
            "Metal acceleration (Apple Silicon)", apple_silicon,
            "native Ollama uses Metal automatically" if apple_silicon else
            "Intel Mac — the stack runs, but inference is CPU-only",
        ))

        if not self.compose_file.is_file():
            checks.append(PrereqCheck("docker-compose.yml found", False,
                                      f"expected at {self.compose_file}"))
        else:
            checks.append(PrereqCheck("docker-compose.yml found", True, str(self.compose_file)))

        try:
            process.run_capture([str(self.bin_dir / "colima"), "status"], env=self._env())
            checks.append(PrereqCheck("Container runtime (colima) running", True))
        except Exception:
            checks.append(PrereqCheck(
                "Container runtime (colima) running", False,
                "started automatically by Start — nothing to do",
            ))
        return checks

    # ---- lifecycle overrides ----------------------------------------------
    def _preflight(self, on_output: OutputCallback) -> None:
        missing = [b for b in _RUNTIME_BINS if not (self.bin_dir / b).is_file()]
        if missing:
            raise BackendError(
                f"Portable runtime incomplete — missing {', '.join(missing)} in "
                f"{self.bin_dir}. Re-install from a macOS bundle."
            )
        self._ensure_colima(on_output)
        self._ensure_native_ollama(on_output)

    def _ensure_colima(self, on_output: OutputCallback) -> None:
        env = self._env()
        try:
            process.run_capture([str(self.bin_dir / "colima"), "status"], env=env)
            on_output(">> Container runtime (colima) already running")
            return
        except Exception:
            pass
        on_output(">> Starting the container runtime (colima) — first boot can take a few minutes")
        # --vm-type vz = Apple Virtualization.framework: faster than qemu and
        # present on every macOS 13+ machine, no extra dependency.
        process.run_command(
            [str(self.bin_dir / "colima"), "start", "--vm-type", "vz"],
            on_output, env=env,
        )

    def _ensure_native_ollama(self, on_output: OutputCallback) -> None:
        url = f"http://localhost:{self.config.ollama_port}"
        if process.probe_http(url):
            on_output(">> Native Ollama already serving (Metal on Apple Silicon)")
            return
        on_output(">> Starting native Ollama (Metal on Apple Silicon)")
        env = self._env()
        env.update(_OLLAMA_TUNING)
        # BIND on all interfaces: the API container inside the colima VM
        # reaches the host via host.docker.internal/host-gateway, which does
        # not route to the host's 127.0.0.1 under every network mode.
        env["OLLAMA_HOST"] = f"0.0.0.0:{self.config.ollama_port}"
        self._ollama_log.parent.mkdir(parents=True, exist_ok=True)
        # Detached from the GUI (start_new_session) so closing the control
        # panel doesn't kill inference; output to its own log file, which the
        # Logs view tails for the "ollama" selection.
        with open(self._ollama_log, "ab") as log_fh:
            proc = subprocess.Popen(
                [str(self.bin_dir / "ollama"), "serve"],
                stdout=log_fh, stderr=subprocess.STDOUT,
                env=env, start_new_session=True,
            )
        self._ollama_pidfile.write_text(str(proc.pid))
        get_logger().info("native ollama started (pid %d, log %s)", proc.pid, self._ollama_log)

    def _compose_up(self, on_output: OutputCallback) -> None:
        on_output(f">> macOS mode — api:{self.config.api_port} "
                  f"ollama:{self.config.ollama_port} (native/Metal) "
                  f"qdrant:{self.config.qdrant_port}")
        # Stdin override, same mechanism as the Linux GPU override:
        #   - replace api's depends_on wholesale (!override — NOT !reset,
        #     which unsets the node and ignores the replacement value;
        #     verified against compose config): drop the ollama dependency
        #     (that container never runs on macOS) but keep waiting on
        #     qdrant's health
        #   - point the API at the host's native Ollama; host.docker.internal
        #     is mapped explicitly via host-gateway so it resolves under
        #     colima, not only under Docker Desktop
        # `up -d qdrant api` (not bare `up`) keeps compose from creating the
        # ollama container at all.
        override = (
            "services:\n"
            "  api:\n"
            "    depends_on: !override\n"
            "      qdrant:\n"
            "        condition: service_healthy\n"
            "    environment:\n"
            f"      - OLLAMA_URL=http://host.docker.internal:{self.config.ollama_port}\n"
            "    extra_hosts:\n"
            "      - \"host.docker.internal:host-gateway\"\n"
        )
        process.run_command(
            self._compose_cmd("-f", "-", "up", "-d", "qdrant", "api"),
            on_output, cwd=self.app_root, env=self._env(), input_text=override,
        )

    @_logged("stop")
    def stop(self, on_output: OutputCallback) -> None:
        on_output(">> Stopping containers")
        process.run_command(self._compose_cmd("down"), on_output,
                            cwd=self.app_root, env=self._env(), check=False)
        self._stop_native_ollama(on_output)
        on_output(">> Stopping the container runtime (colima)")
        process.run_command([str(self.bin_dir / "colima"), "stop"], on_output,
                            env=self._env(), check=False)

    def _stop_native_ollama(self, on_output: OutputCallback) -> None:
        if not self._ollama_pidfile.is_file():
            return
        try:
            pid = int(self._ollama_pidfile.read_text().strip())
            os.kill(pid, signal.SIGTERM)
            on_output(f">> Stopped native Ollama (pid {pid})")
        except (ValueError, ProcessLookupError, PermissionError) as exc:
            on_output(f"   (native Ollama already gone: {exc})")
        finally:
            self._ollama_pidfile.unlink(missing_ok=True)

    # ---- status / logs ------------------------------------------------------
    def status(self) -> Iterable[ServiceStatus]:
        results = [self._inspect("Qdrant", "qdrant")]
        ollama_up = process.probe_http(f"http://localhost:{self.config.ollama_port}")
        results.append(ServiceStatus(
            "Ollama", running=ollama_up, healthy=ollama_up if ollama_up else None,
            detail="native (Metal)" if ollama_up else "not running",
        ))
        results.append(self._inspect("API", "dffrnt-api"))
        return results

    def stream_logs(self, service: str | None, on_line: OutputCallback):
        if service == "ollama":
            # Native process — its log file, not a container log.
            if not self._ollama_log.is_file():
                raise BackendError(f"No native Ollama log yet at {self._ollama_log} — "
                                   "start the stack first.")
            return process.LogFollower(
                ["tail", "-n", "200", "-f", str(self._ollama_log)], env=self._env())
        # qdrant/api are containers; "all" follows both (native ollama has its
        # own picker entry).
        services = [service] if service else ["qdrant", "api"]
        cmd = self._compose_cmd("logs", "-f", "--tail", "200", *services)
        return process.LogFollower(cmd, cwd=self.app_root, env=self._env())

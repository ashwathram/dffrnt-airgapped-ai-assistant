"""Host detection: OS, architecture, GPU, and which deployment *pathway*
applies.

Two pathways exist by design:

  CONTAINER — Linux and Windows. Qdrant + Ollama + the API all run as
  Docker containers (see deploy/docker-compose.yml), managed via
  `docker compose` exactly like dffrnt_ctrl_panel.sh does today.
  backends.docker_backend.DockerComposeBackend implements this pathway.

  PORTABLE — macOS. Docker's Linux VM has no Metal/GPU passthrough, so a
  containerized Ollama would be CPU-only. The macOS bundle instead carries
  portable, self-contained binaries: Ollama runs as a native host process
  (Metal acceleration is automatic on Apple Silicon), and Qdrant + the API
  run as containers in a bundled portable runtime (colima + lima + the
  static docker CLI). backends.portable_backend.PortableBackend implements
  management; installers.portable_installer.PortableInstaller implements
  first-run deployment.

`detect()` is the single entry point the app calls at startup; everything
else in this module is a building block for it.
"""

from __future__ import annotations

import platform
import shutil
import subprocess
from dataclasses import dataclass
from enum import Enum


class OS(Enum):
    LINUX = "linux"
    WINDOWS = "windows"
    MACOS = "macos"
    UNKNOWN = "unknown"


class Pathway(Enum):
    CONTAINER = "container"  # Linux / Windows — docker compose stack
    PORTABLE = "portable"  # macOS — native Ollama + bundled portable runtime


IMPLEMENTED_PATHWAYS = {Pathway.CONTAINER, Pathway.PORTABLE}

_OS_TO_PATHWAY = {
    OS.LINUX: Pathway.CONTAINER,
    OS.WINDOWS: Pathway.CONTAINER,
    OS.MACOS: Pathway.PORTABLE,
    OS.UNKNOWN: Pathway.CONTAINER,
}


@dataclass(frozen=True)
class PlatformInfo:
    os: OS
    os_version: str
    arch: str
    pathway: Pathway
    docker_present: bool
    has_nvidia_gpu: bool

    @property
    def pathway_implemented(self) -> bool:
        return self.pathway in IMPLEMENTED_PATHWAYS

    @property
    def is_apple_silicon(self) -> bool:
        """arm64 Mac — native Ollama uses Metal automatically. An Intel Mac
        still works on the portable pathway, but inference is CPU-only."""
        return self.os is OS.MACOS and self.arch.lower() in ("arm64", "aarch64")


def detect_os() -> OS:
    system = platform.system().lower()
    if system == "linux":
        return OS.LINUX
    if system == "windows":
        return OS.WINDOWS
    if system == "darwin":
        return OS.MACOS
    return OS.UNKNOWN


def detect_docker_present() -> bool:
    return shutil.which("docker") is not None


def detect_nvidia_gpu() -> bool:
    """Best-effort GPU probe, mirroring install-prerequisites.sh's own check
    (`nvidia-smi` on the PATH and responding). Never raises — a probe that
    can't run just means "no GPU detected", not an installer crash.
    """
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        return False
    try:
        result = subprocess.run(
            [nvidia_smi],
            capture_output=True,
            timeout=5,
            check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def detect() -> PlatformInfo:
    os_ = detect_os()
    return PlatformInfo(
        os=os_,
        os_version=platform.release(),
        arch=platform.machine(),
        pathway=_OS_TO_PATHWAY[os_],
        docker_present=detect_docker_present(),
        has_nvidia_gpu=detect_nvidia_gpu(),
    )

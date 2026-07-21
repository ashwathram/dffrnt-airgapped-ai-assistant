"""PORTABLE-pathway installer (macOS): deploys the bundle AND the portable
runtime it needs — no Docker Desktop, no Homebrew, nothing system-wide.

The macOS dist/ layout (produced by the VS Code packaging jobs) is:

    dist/
      dffrnt-offline.tar.gz     the ordinary bundle (package.sh)
      installer/                this GUI, shipped next to the bundle
      portable/macos/           deploy/package-macos-portable.sh output:
        bin/ollama              native Ollama (Metal automatic on Apple Silicon)
        bin/colima, bin/limactl, share/lima/…   portable container runtime
        bin/docker, bin/docker-compose          static docker CLI + compose plugin

install() extends the container-pathway flow at its seams: after unpacking
the bundle it copies portable/macos into <dest>/portable, wires the compose
plugin into a contained DOCKER_CONFIG, boots colima, then loads only the
Qdrant + app images (the containerized-Ollama image is skipped — Ollama
runs natively for Metal; see backends/portable_backend.py). First start is
PortableBackend.start(), the same code path the Manage tab uses.
"""

from __future__ import annotations

import platform
import shutil
import stat
from pathlib import Path

from ..backends import PrereqCheck
from ..backends.portable_backend import _RUNTIME_BINS, PortableBackend
from ..config import load_config
from ..logging_setup import get_logger
from . import InstallError, OutputCallback
from .docker_installer import DockerInstaller


def find_portable_runtime(near: list[Path]) -> Path | None:
    """Locate the shipped portable/macos directory: next to the bundle /
    dist / the GUI package — mirroring find_bundles' search spirit."""
    gui_dist = Path(__file__).resolve().parent.parent.parent  # dist/ when shipped
    for base in [*near, gui_dist, Path.cwd(), Path.cwd() / "dist"]:
        candidate = base / "portable" / "macos"
        if (candidate / "bin" / "ollama").is_file():
            return candidate
    return None


class PortableInstaller(DockerInstaller):
    """Overrides DockerInstaller's pathway seams; the install flow itself
    (stop old stack, config preservation, unpack, load, first start) is
    inherited unchanged."""

    def __init__(self):
        self._staged_backend: PortableBackend | None = None  # set during install

    # ---- prerequisites ----------------------------------------------------
    def check_prerequisites(self) -> list[PrereqCheck]:
        logger = get_logger()
        logger.info("install.check_prerequisites: starting (portable/macOS)")
        checks = []

        is_mac = platform.system().lower() == "darwin"
        checks.append(PrereqCheck(
            "macOS host", is_mac,
            "" if is_mac else "the portable pathway only runs on macOS",
        ))

        apple_silicon = platform.machine().lower() in ("arm64", "aarch64")
        checks.append(PrereqCheck(
            "Metal acceleration (Apple Silicon)", apple_silicon,
            "native Ollama uses Metal automatically" if apple_silicon else
            "Intel Mac — install works, but inference is CPU-only",
        ))

        runtime = find_portable_runtime([])
        if runtime is None:
            checks.append(PrereqCheck(
                "Portable runtime found (portable/macos)", False,
                "ship dist/portable/macos next to the bundle — produced by "
                "deploy/package-macos-portable.sh (VS Code task: "
                "'Package: macOS deployment')",
            ))
        else:
            missing = [b for b in _RUNTIME_BINS if not (runtime / "bin" / b).is_file()]
            checks.append(PrereqCheck(
                "Portable runtime found (portable/macos)", not missing,
                str(runtime) if not missing else
                f"{runtime} is incomplete — missing {', '.join(missing)}",
            ))

        for check in checks:
            logger.info("install.check_prerequisites: %s = %s%s",
                        check.name, "ok" if check.ok else "MISSING",
                        f" ({check.detail})" if check.detail else "")
        return checks

    # ---- pathway seams (see DockerInstaller) ------------------------------
    def _backend_for(self, app_root: Path) -> PortableBackend:
        return PortableBackend(app_root, load_config(app_root))

    def _image_tars(self, images_dir: Path) -> list[Path]:
        # Skip the containerized-Ollama image: Ollama runs natively on macOS
        # (that's the whole point of this pathway). package.sh names image
        # tars by mangling "ollama/ollama:<v>" -> "ollama_ollama_<v>.tar".
        tars = super()._image_tars(images_dir)
        kept = [t for t in tars if "ollama" not in t.name.lower()]
        return kept

    def _load_env(self) -> dict | None:
        assert self._staged_backend is not None, "_post_unpack must run before image load"
        return self._staged_backend._env()

    def _post_unpack(self, bundle: Path, dest: Path, out: OutputCallback) -> None:
        out(">> Staging the portable runtime (native Ollama + colima)")
        runtime = find_portable_runtime([bundle.parent, dest])
        if runtime is None:
            raise InstallError(
                "portable/macos runtime not found next to the bundle. Package it "
                "with deploy/package-macos-portable.sh (VS Code: 'Package: macOS "
                "deployment') and keep dist/ together when transferring."
            )

        target = dest / "portable"
        # copy bin/ + share/ (lima guest assets resolve relative to limactl:
        # bin/../share/lima), preserving an existing colima/lima state dir on
        # an update — wiping it would orphan a running VM.
        for sub in ("bin", "share"):
            src = runtime / sub
            if not src.is_dir():
                continue
            dst = target / sub
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
        for binary in (target / "bin").iterdir():
            binary.chmod(binary.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        out(f"   runtime staged into {target}")

        # The docker CLI discovers the compose plugin via $DOCKER_CONFIG/
        # cli-plugins; DOCKER_CONFIG is contained under portable/ (see
        # PortableBackend._env), so wire it there.
        plugins = target / "docker-config" / "cli-plugins"
        plugins.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target / "bin" / "docker-compose", plugins / "docker-compose")
        (plugins / "docker-compose").chmod(0o755)

        # Boot the runtime now — `docker load` (next install stage) needs a
        # daemon. Reuses the exact code path Manage's Start uses.
        self._staged_backend = self._backend_for(dest)
        self._staged_backend._ensure_colima(out)

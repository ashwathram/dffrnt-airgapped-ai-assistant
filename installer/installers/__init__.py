"""The Installer interface — first-run deployment (the retired
deploy/install.sh shell script's job, absorbed here; both the panel's
Install view and the CLI `install` command drive it).

Same pathway split as backends/: DockerInstaller for the CONTAINER pathway
(Linux/Windows), PortableInstaller for macOS. The install flow is
distinct from management because it runs BEFORE an app root exists — the
panel/CLI drive an Installer, and only after install() succeeds is a
Backend constructed against the new app root (the panel server re-points
its Context; see web/server.py's install verb).

Shipping note: for install-from-scratch to work on a box that has nothing
yet, the frozen dffrnt-manager binary travels NEXT TO the bundle tarball
in dist/ (package.sh puts it there), not only inside the bundle — the
tarball's contents don't exist until install runs. In a dev checkout it
can also (re)install over deploy/ from a locally packaged dist/.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..backends import PrereqCheck

OutputCallback = Callable[[str], None]


class InstallError(RuntimeError):
    """Expected install failures (no bundle, docker missing, ...) — shown
    as a message, not a traceback."""


@dataclass(frozen=True)
class BundleInfo:
    """What we can tell the operator about a bundle before unpacking it."""
    path: Path
    target_system: str  # "offline" | "online"/"aws" (from the tarball's bundle.conf)
    size_bytes: int


class Installer(ABC):
    """One verb plus discovery/validation. install() streams progress via
    OutputCallback and is expected to run in a BackgroundJob, exactly like
    Backend's lifecycle methods."""

    @abstractmethod
    def check_prerequisites(self) -> list[PrereqCheck]:
        """Non-mutating. What install() needs before it can run — the
        pre-install gate (Docker Engine + Compose v2)."""

    @abstractmethod
    def inspect_bundle(self, bundle: Path) -> BundleInfo:
        """Validate a candidate tarball and summarize it. Raises
        InstallError if it isn't a usable bundle."""

    @abstractmethod
    def install(self, bundle: Path, dest: Path, on_output: OutputCallback,
                *, keep_config: bool = True) -> Path:
        """Deploy `bundle` into `dest` and return the resulting app root:
        stop any old stack, preserve (keep_config=True) or
        archive-and-overwrite the edited config, unpack, load images, first
        start. Callers resolve keep_config BEFORE starting (panel modal /
        CLI flag) — a background job must never block on a question."""


def make_installer(platform_info) -> "Installer":
    """The one place a PlatformInfo picks an Installer implementation,
    shared by the panel server and the CLI (same pattern as
    backends.make_backend)."""
    from ..platform_detect import Pathway
    from .docker_installer import DockerInstaller
    from .portable_installer import PortableInstaller

    if platform_info.pathway is Pathway.PORTABLE:
        return PortableInstaller()
    return DockerInstaller()


def find_bundles(search_dirs: list[Path]) -> list[Path]:
    """dffrnt-*.tar.gz candidates near the app, newest first — auto-detects
    a tarball sitting next to the manager binary or the checkout."""
    seen: dict[Path, None] = {}
    for d in search_dirs:
        if d.is_dir():
            for p in sorted(d.glob("dffrnt-*.tar.gz")):
                seen.setdefault(p.resolve())
    return sorted(seen, key=lambda p: p.stat().st_mtime, reverse=True)

"""The Installer interface — first-run deployment, the GUI counterpart of
deploy/install.sh (as backends/ is the counterpart of dffrnt_ctrl_panel.sh).

Same pathway split as backends/: DockerInstaller for the CONTAINER pathway
(Linux/Windows), PortableInstaller stubbed for macOS. The install flow is
distinct from management because it runs BEFORE an app root exists — the
InstallView owns an Installer, and only after install() succeeds does the
app construct a Backend against the new app root (see app.py's
on_installed re-point).

Shipping note: for install-from-scratch to work on a box that has nothing
yet, this GUI must travel NEXT TO the bundle tarball in dist/ (like
install.sh does), not inside it — the tarball's contents don't exist until
install runs. In a dev checkout it can also (re)install over deploy/ from
a locally packaged dist/.
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
        install.sh [1/4] gate."""

    @abstractmethod
    def inspect_bundle(self, bundle: Path) -> BundleInfo:
        """Validate a candidate tarball and summarize it. Raises
        InstallError if it isn't a usable bundle."""

    @abstractmethod
    def install(self, bundle: Path, dest: Path, on_output: OutputCallback,
                *, keep_config: bool = True) -> Path:
        """Deploy `bundle` into `dest` and return the resulting app root.
        Mirrors install.sh: stop old stack, preserve (keep_config=True) or
        archive-and-overwrite the edited config, unpack, load images, first
        start. The view resolves keep_config with a dialog BEFORE starting,
        where install.sh prompts mid-run."""


def find_bundles(search_dirs: list[Path]) -> list[Path]:
    """dffrnt-*.tar.gz candidates near the app, newest first — the same
    auto-detection install.sh does for a tarball sitting next to it."""
    seen: dict[Path, None] = {}
    for d in search_dirs:
        if d.is_dir():
            for p in sorted(d.glob("dffrnt-*.tar.gz")):
                seen.setdefault(p.resolve())
    return sorted(seen, key=lambda p: p.stat().st_mtime, reverse=True)

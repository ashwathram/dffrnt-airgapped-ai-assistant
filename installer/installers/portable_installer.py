"""PORTABLE-pathway installer (macOS) — NOT IMPLEMENTED YET.

Counterpart of backends/portable_backend.py, same reasoning (see that
module's docstring for why macOS can't use the container pathway). When
phase 2 lands, install() here will place the vendored native Ollama binary
and the portable Qdrant runtime from the macOS-specific bundle instead of
docker-loading images.
"""

from __future__ import annotations

from pathlib import Path

from ..backends import PrereqCheck
from ..logging_setup import get_logger
from . import BundleInfo, Installer, OutputCallback

_NOT_IMPLEMENTED = (
    "The macOS install pathway (native Ollama + portable Qdrant runtime) "
    "isn't implemented yet. See installer/installers/portable_installer.py."
)


def _unavailable(stage: str) -> None:
    get_logger().warning("%s: unavailable — %s", stage, _NOT_IMPLEMENTED)
    raise NotImplementedError(_NOT_IMPLEMENTED)


class PortableInstaller(Installer):
    def check_prerequisites(self) -> list[PrereqCheck]:
        get_logger().warning("install.check_prerequisites: %s", _NOT_IMPLEMENTED)
        return [PrereqCheck("macOS install pathway implemented", False, _NOT_IMPLEMENTED)]

    def inspect_bundle(self, bundle: Path) -> BundleInfo:
        _unavailable("install.inspect_bundle")

    def install(self, bundle: Path, dest: Path, on_output: OutputCallback,
                *, keep_config: bool = True) -> Path:
        _unavailable("install")

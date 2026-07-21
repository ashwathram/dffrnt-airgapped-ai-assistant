"""CONTAINER-pathway installer (Linux/Windows): a port of deploy/install.sh
stage for stage. Treat that script as the reference implementation, same
rule as docker_backend.py vs dffrnt_ctrl_panel.sh.

Differences from the script, all deliberate:
  - tarfile instead of a `tar` binary (works on Windows; one less prereq).
  - The operator picks bundle + destination in the GUI, so the "exactly one
    dffrnt-*.tar.gz next to me" auto-detection lives in the view, not here.
  - The config-overwrite question is answered by the view (a dialog) BEFORE
    install starts, via keep_config — install.sh prompts mid-run instead.
  - First start is DockerComposeBackend.start() — the same code path the
    Manage tab uses — rather than shelling out to dffrnt_ctrl_panel.sh.
"""

from __future__ import annotations

import shutil
import tarfile
from pathlib import Path

from .. import process
from ..backends import PrereqCheck
from ..backends.docker_backend import DockerComposeBackend
from ..config import load_config
from ..logging_setup import get_logger, with_logging
from . import BundleInfo, InstallError, Installer, OutputCallback


class DockerInstaller(Installer):
    def check_prerequisites(self) -> list[PrereqCheck]:
        """install.sh's [1/4] gate, minus tar (tarfile is stdlib) and curl
        (probe_http is stdlib) — Docker + Compose is all that's left."""
        logger = get_logger()
        logger.info("install.check_prerequisites: starting")
        checks = []
        try:
            version = process.run_capture(["docker", "--version"])
            checks.append(PrereqCheck("Docker installed", True, version))
            try:
                process.run_capture(["docker", "info"])
                checks.append(PrereqCheck("Docker daemon running", True))
            except Exception as exc:
                checks.append(PrereqCheck(
                    "Docker daemon running", False,
                    f"start Docker and ensure your user can access it — {exc}",
                ))
            try:
                version = process.run_capture(["docker", "compose", "version"])
                checks.append(PrereqCheck("Compose v2 plugin", True, version))
            except Exception:
                checks.append(PrereqCheck("Compose v2 plugin", False,
                                          "install the Docker Compose v2 plugin"))
        except Exception:
            checks.append(PrereqCheck(
                "Docker installed", False,
                "install Docker Engine + the Compose v2 plugin "
                "(https://docs.docker.com/engine/install/)",
            ))
        for check in checks:
            logger.info("install.check_prerequisites: %s = %s%s",
                        check.name, "ok" if check.ok else "MISSING",
                        f" ({check.detail})" if check.detail else "")
        return checks

    def inspect_bundle(self, bundle: Path) -> BundleInfo:
        """Cheap validation without unpacking: it must be a gzipped tar with
        a top-level bundle.conf (every package.sh bundle has one)."""
        if not bundle.is_file():
            raise InstallError(f"Bundle not found: {bundle}")
        try:
            with tarfile.open(bundle, "r:gz") as tar:
                conf_member = None
                for member in tar:
                    parts = Path(member.name).parts
                    # package.sh tars a single top-level dir; --strip-components=1
                    # equivalent means bundle.conf sits at <topdir>/bundle.conf.
                    if len(parts) == 2 and parts[1] == "bundle.conf":
                        conf_member = member
                        break
                if conf_member is None:
                    raise InstallError(
                        f"{bundle.name} has no bundle.conf — not a dffrnt bundle "
                        "produced by deploy/package.sh."
                    )
                fh = tar.extractfile(conf_member)
                text = fh.read().decode() if fh else ""
        except tarfile.TarError as exc:
            raise InstallError(f"Could not read {bundle.name}: {exc}") from exc
        target_system = "online"
        for line in text.splitlines():
            if line.startswith("TARGET_SYSTEM="):
                target_system = line.split("=", 1)[1].strip().strip("\"'").lower()
        return BundleInfo(path=bundle, target_system=target_system,
                          size_bytes=bundle.stat().st_size)

    def install(self, bundle: Path, dest: Path, on_output: OutputCallback,
                *, keep_config: bool = True) -> Path:
        logger = get_logger()
        logger.info("install: starting (bundle=%s dest=%s keep_config=%s)",
                    bundle, dest, keep_config)
        out = with_logging("install", on_output)
        try:
            self._install(bundle, dest, out, keep_config)
        except Exception:
            logger.exception("install: failed")
            raise
        logger.info("install: complete (app_root=%s)", dest)
        return dest

    # ---- pathway seams ---------------------------------------------------
    # PortableInstaller (macOS) subclasses this and overrides these; the
    # install flow in _install stays single-sourced (same pattern as
    # DockerComposeBackend's seams).

    def _backend_for(self, app_root: Path):
        """The Backend used to stop an old stack / first-start the new one."""
        return DockerComposeBackend(app_root, load_config(app_root))

    def _post_unpack(self, bundle: Path, dest: Path, out: OutputCallback) -> None:
        """Hook between unpack and image load. The portable pathway stages
        its bundled runtime + boots colima here (images can't load before
        the runtime exists). No-op on the container pathway."""

    def _image_tars(self, images_dir: Path) -> list[Path]:
        """Which image tarballs to docker-load. The portable pathway skips
        the containerized-Ollama image (Ollama runs natively on macOS)."""
        return sorted(images_dir.glob("*.tar")) if images_dir.is_dir() else []

    def _load_env(self) -> dict | None:
        """Environment for `docker load` — the portable pathway points it at
        the bundled runtime's daemon."""
        return None

    def _install(self, bundle: Path, dest: Path, out: OutputCallback,
                 keep_config: bool) -> None:
        info = self.inspect_bundle(bundle)  # re-validate; cheap
        out(f">> Installing from {bundle.name} into {dest}")

        # ---- update handling: stop the old stack, protect the config ----
        # (all no-ops on a fresh install, same as install.sh)
        preserved_config = None
        if (dest / "docker-compose.yml").is_file():
            out(f">> Updating an existing install in {dest} — stopping the running stack first")
            try:
                old_backend = self._backend_for(dest)
                old_backend.stop(out)
            except Exception as exc:
                out(f"   (could not stop the old stack cleanly: {exc} — continuing)")
        existing_config = dest / "config.toml"
        if existing_config.is_file():
            if keep_config:
                out("   keeping the existing config.toml")
                preserved_config = existing_config.read_bytes()
            else:
                out("   overwriting — archiving the current config as config.toml.old")
                shutil.copy2(existing_config, dest / "config.toml.old")

        # ---- unpack (tar --strip-components=1 equivalent) ---------------
        out(">> [2/4] Unpacking bundle")
        dest.mkdir(parents=True, exist_ok=True)
        with tarfile.open(bundle, "r:gz") as tar:
            members = tar.getmembers()
            stripped = []
            for member in members:
                parts = Path(member.name).parts
                if len(parts) <= 1:
                    continue  # the top-level dir entry itself
                member.name = str(Path(*parts[1:]))
                stripped.append(member)
            # Python 3.12+: the "data" filter blocks path traversal, abs
            # paths, and specials — protection plain `tar -xzf` never had.
            tar.extractall(dest, members=stripped, filter="data")
        out(f"   unpacked {len(stripped)} entries")
        if preserved_config is not None:
            (dest / "config.toml").write_bytes(preserved_config)
            out("   restored the preserved config.toml over the bundle default")

        self._post_unpack(bundle, dest, out)

        # ---- load container image(s) ------------------------------------
        out(">> [3/4] Loading container image(s)")
        images_dir = dest / "images"
        image_tars = self._image_tars(images_dir)
        if not image_tars:
            # AWS/online bundles ship no images dir — compose pulls instead.
            out(f"   no image tarballs in {images_dir} (online bundle — Docker will pull)")
        for image_tar in image_tars:
            process.run_command(["docker", "load", "-i", str(image_tar)], out,
                                env=self._load_env())

        # ---- first start, via the same backend the Manage tab uses ------
        out(">> [4/4] Starting the stack")
        backend = self._backend_for(dest)
        backend.start(out)
        out(f">> Installed ({info.target_system}). The app lives in: {dest}")


def default_install_dest() -> Path:
    """install.sh's default: ./dffrnt next to the installer. In a dev
    checkout that's <repo>/dffrnt; from a frozen binary it's next to the
    executable — writable in both cases, unlike a system dir."""
    return Path.cwd() / "dffrnt"


def is_installed(app_root: Path) -> bool:
    """Heuristic install.sh also relies on: an app root is 'installed' when
    the compose file is present."""
    return (app_root / "docker-compose.yml").is_file()

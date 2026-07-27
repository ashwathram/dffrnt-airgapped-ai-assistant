"""Host-side operations on an Ollama model store (the ``ollama_models``
directory both pathways use: bind-mounted into the container on
Linux/Windows, pointed at via OLLAMA_MODELS by the native macOS process).

A store is two directories:

    manifests/<registry>/<namespace...>/<name>/<tag>   tiny JSON index
    blobs/sha256-<hex>                                 content-addressed data

The manifest names the blobs (config digest + layer digests), so a model is
fully described by one manifest file plus the blobs it references. That
makes offline transfer a plain file copy: this module packs exactly that
subset into an uncompressed tar (model weights are already-quantized and
near-incompressible — gzip would burn minutes for ~1%), and merges such a
tar back into a store additively (blobs dedupe by hash).

Everything here is filesystem-only and safe to call with the stack down.
No UI, no docker — backends wire these into the panel and the CLI.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

_DEFAULT_REGISTRY = "registry.ollama.ai"
_DEFAULT_NAMESPACE = "library"
_BLOB_RE = re.compile(r"^sha256-[0-9a-f]{64}$")
# Ollama model names: [host/][namespace/]name[:tag], all from this charset.
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*(:[A-Za-z0-9._-]+)?$")
# Filesystems with the 4 GiB single-file ceiling. exFAT is fine.
_FAT_FS = {"vfat", "msdos", "fat", "fat32"}
FAT_FILE_LIMIT = 4 * 1024**3

# The store's model-name filter for the LLM picker: embedding models must
# not be offered as chat models. Heuristic markers cover the embedders
# Ollama actually distributes (bge-m3, nomic-embed-text, mxbai-embed-large,
# snowflake-arctic-embed, all-minilm, granite-embedding, paraphrase-*);
# callers additionally exclude the configured embed_model by name.
_EMBED_MARKERS = ("embed", "bge-", "all-minilm", "paraphrase-")

KEEP_FILE = "models.keep"


class ModelStoreError(RuntimeError):
    """Expected failures (bad tar, hash mismatch, missing blob...) with an
    operator-readable message — the panel/CLI show str(exc), never a traceback."""


@dataclass(frozen=True)
class ModelInfo:
    name: str          # ollama-style, e.g. "qwen3:14b" or "hf.co/user/repo:Q4"
    size_bytes: int    # sum of the blobs the manifest references


# ---- name <-> manifest path -------------------------------------------------

def with_tag(name: str) -> str:
    return name if ":" in name else f"{name}:latest"


def looks_like_embedder(name: str) -> bool:
    base = name.rsplit("/", 1)[-1].split(":", 1)[0].lower()
    return any(marker in base for marker in _EMBED_MARKERS)


def name_to_manifest_rel(name: str) -> PurePosixPath:
    """``qwen3:14b`` -> manifests/registry.ollama.ai/library/qwen3/14b;
    ``hf.co/user/repo:Q4`` -> manifests/hf.co/user/repo/Q4. A first path
    component containing a dot is an explicit registry host (hf.co, ...)."""
    if not _NAME_RE.match(name):
        raise ModelStoreError(f"'{name}' is not a valid model name")
    bare, _, tag = name.partition(":")
    tag = tag or "latest"
    parts = bare.split("/")
    if "." in parts[0] and len(parts) > 1:
        return PurePosixPath("manifests", *parts, tag)
    if len(parts) == 1:
        parts = [_DEFAULT_NAMESPACE, *parts]
    return PurePosixPath("manifests", _DEFAULT_REGISTRY, *parts, tag)


def manifest_rel_to_name(rel: PurePosixPath) -> str:
    """Inverse of name_to_manifest_rel; ``rel`` is relative to manifests/."""
    *dirs, tag = rel.parts
    if dirs and dirs[0] == _DEFAULT_REGISTRY:
        dirs = dirs[1:]
        if dirs and dirs[0] == _DEFAULT_NAMESPACE:
            dirs = dirs[1:]
    return "/".join(dirs) + ":" + tag


# ---- reading a store --------------------------------------------------------

def _digests_from_doc(doc: dict, label: str) -> list[str]:
    """The blob digests (config + layers) a parsed manifest names, each as a
    ``sha256-<hex>`` blob filename. ``label`` only names the manifest in errors."""
    digests = [doc.get("config", {}).get("digest", "")]
    digests += [layer.get("digest", "") for layer in doc.get("layers", [])]
    out = []
    for digest in digests:
        if not digest:
            continue
        fname = digest.replace("sha256:", "sha256-", 1)
        if not _BLOB_RE.match(fname):
            raise ModelStoreError(f"manifest {label} names a non-sha256 digest: {digest}")
        out.append(fname)
    return out


def manifest_digests(manifest_path: Path) -> list[str]:
    """Blob digests a manifest file references, as ``sha256-<hex>`` filenames."""
    try:
        doc = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ModelStoreError(f"unreadable manifest {manifest_path.name}: {exc}") from exc
    return _digests_from_doc(doc, manifest_path.name)


def list_models(store: Path) -> list[ModelInfo]:
    """Every model a manifest file names, across ALL registries — including
    hf.co/... pulls, which the library-only walks elsewhere miss, and models
    ``ollama list`` hides because a blob is missing (size then reflects only
    the blobs present)."""
    manifests_root = store / "manifests"
    if not manifests_root.is_dir():
        return []
    infos = []
    for path in sorted(manifests_root.rglob("*")):
        # A manifest is a file at least registry/name/tag deep.
        if not path.is_file() or len(path.relative_to(manifests_root).parts) < 3:
            continue
        rel = PurePosixPath(*path.relative_to(manifests_root).parts)
        try:
            digests = manifest_digests(path)
        except ModelStoreError:
            digests = []  # broken manifest: list it (prunable), size unknown
        size = sum(
            (store / "blobs" / d).stat().st_size
            for d in digests if (store / "blobs" / d).is_file()
        )
        infos.append(ModelInfo(name=manifest_rel_to_name(rel), size_bytes=size))
    return infos


def model_present(store: Path, name: str) -> bool:
    return (store / name_to_manifest_rel(name)).is_file()


# ---- export -----------------------------------------------------------------

def export_model(store: Path, name: str, dest_tar: Path, on_output) -> None:
    """Pack one model (manifest + every referenced blob) into an
    uncompressed tar at ``dest_tar``, verifying blob presence and warning
    guards (FAT32 4 GiB ceiling, free space) before writing a byte."""
    manifest = store / name_to_manifest_rel(name)
    if not manifest.is_file():
        raise ModelStoreError(f"model '{name}' is not in the store at {store}")
    digests = manifest_digests(manifest)
    missing = [d for d in digests if not (store / "blobs" / d).is_file()]
    if missing:
        raise ModelStoreError(
            f"model '{name}' is incomplete — {len(missing)} blob(s) missing from "
            f"{store / 'blobs'} (re-pull it, then export)")

    total = sum((store / "blobs" / d).stat().st_size for d in digests)
    dest_dir = dest_tar.parent
    fs = fs_type(dest_dir)
    if fs in _FAT_FS and total >= FAT_FILE_LIMIT:
        raise ModelStoreError(
            f"the destination filesystem is {fs.upper()} (FAT32-family), which cannot "
            f"hold a single file over 4 GiB — this export is {human_size(total)}. "
            "Reformat the drive as exFAT (or ext4) and retry.")
    free = shutil.disk_usage(dest_dir).free
    if free < total:
        raise ModelStoreError(
            f"not enough space at {dest_dir}: export needs {human_size(total)}, "
            f"only {human_size(free)} free")

    on_output(f">> Exporting {name} ({human_size(total)}, {len(digests)} blobs) -> {dest_tar}")
    tmp = dest_tar.with_name(dest_tar.name + ".partial")
    try:
        with tarfile.open(tmp, "w") as tar:  # plain tar: weights don't compress
            tar.add(manifest, arcname=str(name_to_manifest_rel(name)), recursive=False)
            for i, digest in enumerate(digests, 1):
                blob = store / "blobs" / digest
                on_output(f"   [{i}/{len(digests)}] {digest[:19]}… ({human_size(blob.stat().st_size)})")
                tar.add(blob, arcname=f"blobs/{digest}", recursive=False)
        os.replace(tmp, dest_tar)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    on_output(f">> Done. Move {dest_tar.name} to the target machine and use "
              "Models -> Import there.")


# ---- import -----------------------------------------------------------------

def import_tarball(tar_path: Path, store: Path, on_output) -> list[str]:
    """Merge a model tar (as written by export_model) into ``store``.
    Validates member paths, verifies every blob's content hash against its
    filename (catches USB corruption before Ollama ever sees the model),
    and checks that no imported manifest references a blob that is neither
    in the tar nor already in the store. Returns the imported model names."""
    if not tar_path.is_file():
        raise ModelStoreError(f"no such file: {tar_path}")

    with tarfile.open(tar_path, "r:*") as tar:   # tolerate a gzipped tar too
        members = [m for m in tar.getmembers() if m.isfile()]
        blob_members, manifest_members = [], []
        for m in members:
            parts = PurePosixPath(m.name).parts
            if parts[0] == "blobs" and len(parts) == 2 and _BLOB_RE.match(parts[1]):
                blob_members.append(m)
            elif parts[0] == "manifests" and len(parts) >= 4:
                manifest_members.append(m)
            else:
                raise ModelStoreError(
                    f"{tar_path.name} is not a model export — unexpected member "
                    f"'{m.name}' (expected only manifests/... and blobs/sha256-...)")
        if not manifest_members:
            raise ModelStoreError(f"{tar_path.name} contains no model manifest")

        # Fast path / no-op: if every model in the tar is ALREADY fully in the
        # store (manifest byte-identical + all its blobs present), there is
        # nothing to do. Skip the (multi-GB) extract entirely AND avoid writing
        # into the store — which matters because a store the Ollama container
        # has run against is owned by root (it chowns manifests/ + blobs/), so
        # a host-side rename over an identical file would fail with EACCES for
        # no reason. This is the common "re-import what I already have" case.
        already = _already_present(tar, manifest_members, store)
        if already is not None:
            on_output(f">> {', '.join(already)} already in the store — nothing to import.")
            return already

        payload = sum(m.size for m in members)
        store.mkdir(parents=True, exist_ok=True)
        free = shutil.disk_usage(store).free
        # The temp extract lives on the store's filesystem, so transiently
        # need the full payload plus slack even when blobs later dedupe.
        if free < payload + 512 * 1024**2:
            raise ModelStoreError(
                f"not enough space at {store}: import needs {human_size(payload)} "
                f"(+512 MB slack), only {human_size(free)} free")

        tmp = store / f".import-{os.getpid()}-{int(time.time())}"
        try:
            on_output(f">> Unpacking {tar_path.name} ({human_size(payload)})")
            tar.extractall(tmp, members=members, filter="data")

            on_output(f">> Verifying {len(blob_members)} blob checksum(s)")
            for m in blob_members:
                digest = PurePosixPath(m.name).parts[1]
                actual = _sha256_file(tmp / "blobs" / digest)
                if f"sha256-{actual}" != digest:
                    raise ModelStoreError(
                        f"checksum mismatch on {digest[:19]}… — the archive is "
                        "corrupt (re-copy it from the source machine)")

            # Completeness: every digest each manifest names must arrive in
            # this tar or already sit in the store, or the model imports
            # broken and Ollama hides-but-logs it forever.
            names = []
            in_tar = {PurePosixPath(m.name).parts[1] for m in blob_members}
            for m in manifest_members:
                rel = PurePosixPath(m.name).relative_to("manifests")
                for digest in manifest_digests(tmp / PurePosixPath(m.name)):
                    if digest not in in_tar and not (store / "blobs" / digest).is_file():
                        raise ModelStoreError(
                            f"{tar_path.name} is incomplete: manifest "
                            f"{manifest_rel_to_name(rel)} references blob "
                            f"{digest[:19]}… which is neither in the archive nor "
                            "already in the store")
                names.append(manifest_rel_to_name(rel))

            # Commit into the store. Blobs first so a manifest is never
            # visible before the blobs it names. Both moves can hit EACCES
            # when the store is owned by root (the Ollama container) — turn
            # that into one actionable message instead of a raw errno on an
            # opaque temp path.
            try:
                merged, deduped = 0, 0
                for m in blob_members:
                    digest = PurePosixPath(m.name).parts[1]
                    target = store / "blobs" / digest
                    if target.is_file():
                        deduped += 1
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(tmp / "blobs" / digest, target)  # same fs: atomic
                    merged += 1
                for m in manifest_members:
                    src = tmp / PurePosixPath(m.name)
                    target = store / PurePosixPath(m.name)
                    # An identical manifest already in place needs no write
                    # (and the write might be unpermitted) — leave it.
                    if target.is_file() and target.read_bytes() == src.read_bytes():
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(src, target)
            except PermissionError as exc:
                raise ModelStoreError(_ownership_help(store, exc)) from exc
            on_output(f">> Imported {', '.join(names)} "
                      f"({merged} blob(s) added, {deduped} already present)")
            return names
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


def _ownership_help(store: Path, exc: OSError) -> str:
    """The verbose, copy-pasteable remedy for an import blocked by store
    ownership. Kept as one raised string (newlines survive into the panel
    console and the CLI); the store path is interpolated so the commands are
    literally runnable. Deliberately does NOT suggest 'import while stopped'
    — stopping the stack does not un-root a store the container already took,
    so on any deployment that has run, reclaiming ownership is the only fix."""
    return (
        f"Cannot write the imported model into the store at {store} "
        f"({exc.strerror}).\n"
        "\n"
        "WHY: the Ollama container runs as root, so the first time the stack "
        "started it took ownership of the store's manifests/ and blobs/ "
        "directories. Import writes those files from the host as your user, "
        "which root now owns — so the write is denied. (Online pulls and "
        "deletes don't hit this because Ollama performs them from inside the "
        "container, as root; an offline import is the one path that writes "
        "host-side.)\n"
        "\n"
        "FIX — reclaim ownership of the store, then re-run the import:\n"
        "\n"
        "  1. Stop the stack so nothing writes to the store mid-change:\n"
        "       dffrnt-manager stop\n"
        "     (or click Stop on the Manage tab). On the frozen binary use its\n"
        "     path, e.g. ./dffrnt-manager stop.\n"
        "\n"
        "  2. Give the store back to your user (recursively). This needs sudo\n"
        "     because the files are root-owned:\n"
        f"       sudo chown -R \"$(id -un):$(id -gn)\" \"{store}\"\n"
        "\n"
        "  3. Re-run the import — Models -> Import in the panel, or:\n"
        "       dffrnt-manager models import <the-tarball>\n"
        "\n"
        "  4. Start the stack again as usual:\n"
        "       dffrnt-manager start\n"
        "\n"
        "NOTE: the imported model is now permanent, but starting the stack "
        "re-roots the store's files (harmless — Ollama reads them fine), so "
        "importing ANOTHER new model later means repeating steps 1-4. To stop "
        "the re-rooting entirely, run the Ollama container as your host user "
        "(a 'user:' entry on the ollama service in docker-compose.yml) so the "
        "store stays yours and imports need no chown."
    )


def _already_present(tar, manifest_members, store: Path) -> list[str] | None:
    """Names of the tar's models if EVERY one is already fully in ``store``
    (each manifest byte-identical on disk and all its blobs present), else
    None. Reads only the tiny manifest members — no blob extraction — so the
    caller can short-circuit before unpacking anything. Any read/parse hiccup
    returns None, falling back to the safe full import path."""
    names = []
    for m in manifest_members:
        rel = PurePosixPath(m.name)
        target = store / rel
        if not target.is_file():
            return None
        try:
            fh = tar.extractfile(m)
            member_bytes = fh.read() if fh else b""
            if not member_bytes or target.read_bytes() != member_bytes:
                return None
            digests = _digests_from_doc(json.loads(member_bytes), m.name)
        except (OSError, ValueError, ModelStoreError):
            return None
        if any(not (store / "blobs" / d).is_file() for d in digests):
            return None
        names.append(manifest_rel_to_name(rel.relative_to("manifests")))
    return names


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


# ---- the keep file ----------------------------------------------------------
# Start's prune sweeps every cached model the live config doesn't reference —
# right for reclaiming disk on a swap, wrong for a model the operator just
# imported but hasn't switched to yet (on an air-gapped box that deletion is
# unrecoverable without another USB trip). models.keep (one name per line,
# next to config.toml) lists imported models the prune sweep must leave alone.

def read_keep_file(app_root: Path) -> list[str]:
    path = app_root / KEEP_FILE
    if not path.is_file():
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")]


def add_to_keep_file(app_root: Path, names: list[str]) -> None:
    current = read_keep_file(app_root)
    merged = current + [n for n in names if n not in current]
    if merged != current:
        _write_keep_file(app_root, merged)


def remove_from_keep_file(app_root: Path, name: str) -> None:
    current = read_keep_file(app_root)
    kept = [n for n in current if with_tag(n) != with_tag(name)]
    if kept != current:
        _write_keep_file(app_root, kept)


def _write_keep_file(app_root: Path, names: list[str]) -> None:
    path = app_root / KEEP_FILE
    body = ("# Models protected from the start-time prune (imported via the\n"
            "# control panel's Models tab). One name per line.\n"
            + "".join(f"{n}\n" for n in names))
    tmp = path.with_suffix(".tmp")
    tmp.write_text(body, encoding="utf-8")
    os.replace(tmp, path)


# ---- filesystem probing -----------------------------------------------------

def fs_type(path: Path) -> str | None:
    """Best-effort filesystem type for ``path`` (lowercase, e.g. "vfat"),
    None when undeterminable. Used only to warn about FAT32's 4 GiB file
    ceiling before a doomed multi-GB export begins."""
    try:
        target = str(path.resolve())
        if sys.platform.startswith("linux"):
            best, best_fs = "", None
            with open("/proc/mounts", encoding="utf-8") as fh:
                for line in fh:
                    fields = line.split()
                    if len(fields) < 3:
                        continue
                    # Mount points octal-escape spaces as \040.
                    mount = fields[1].replace("\\040", " ")
                    if (target == mount or target.startswith(mount.rstrip("/") + "/")) \
                            and len(mount) > len(best):
                        best, best_fs = mount, fields[2].lower()
            return best_fs
        if sys.platform == "darwin":
            out = subprocess.run(["mount"], capture_output=True, text=True,
                                 timeout=5).stdout
            best, best_fs = "", None
            for match in re.finditer(r" on (.+) \(([^,)]+)", out):
                mount = match.group(1)
                if (target == mount or target.startswith(mount.rstrip("/") + "/")) \
                        and len(mount) > len(best):
                    best, best_fs = mount, match.group(2).lower()
            return best_fs
    except Exception:
        pass
    return None


def human_size(n: int) -> str:
    value = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024:
            return f"{value:,.1f} {unit}"
        value /= 1024
    return f"{value:,.1f} TB"

"""installer/model_store.py: the store walk, tarball export/import
round-trip, and the guards (checksum, completeness, member whitelist) that
keep a corrupt USB copy from ever reaching Ollama. Everything runs against
synthetic stores in tmp_path — no docker, no network, no GUI.
"""

import hashlib
import io
import json
import os
import tarfile

import pytest

from installer import model_store
from installer.config import write_config_value
from installer.model_store import (
    ModelStoreError,
    export_model,
    import_tarball,
    list_models,
    manifest_rel_to_name,
    model_present,
    name_to_manifest_rel,
)


# ---- synthetic store helpers -----------------------------------------------

def _blob(store, data: bytes) -> str:
    digest = f"sha256-{hashlib.sha256(data).hexdigest()}"
    blobs = store / "blobs"
    blobs.mkdir(parents=True, exist_ok=True)
    (blobs / digest).write_bytes(data)
    return digest


def _make_model(store, name: str, *, weights: bytes) -> list[str]:
    """Create a manifest + (config, weights) blobs for `name`; returns digests."""
    config_digest = _blob(store, b"config-of-" + name.encode())
    weights_digest = _blob(store, weights)
    manifest = {
        "schemaVersion": 2,
        "config": {"digest": config_digest.replace("sha256-", "sha256:", 1)},
        "layers": [{"mediaType": "application/vnd.ollama.image.model",
                    "digest": weights_digest.replace("sha256-", "sha256:", 1),
                    "size": len(weights)}],
    }
    path = store / name_to_manifest_rel(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest))
    return [config_digest, weights_digest]


def _quiet(_line):  # on_output sink
    pass


# ---- name <-> path mapping --------------------------------------------------

@pytest.mark.parametrize("name,rel", [
    ("qwen3:14b", "manifests/registry.ollama.ai/library/qwen3/14b"),
    ("bge-m3", "manifests/registry.ollama.ai/library/bge-m3/latest"),
    ("user/model:tag", "manifests/registry.ollama.ai/user/model/tag"),
    ("hf.co/user/repo:Q4_K_M", "manifests/hf.co/user/repo/Q4_K_M"),
])
def test_name_path_round_trip(name, rel):
    assert str(name_to_manifest_rel(name)) == rel
    manifests_rel = name_to_manifest_rel(name).relative_to("manifests")
    assert manifest_rel_to_name(manifests_rel) == model_store.with_tag(name)


def test_invalid_names_rejected():
    for bad in ("", "../escape", "a b", 'x"y'):
        with pytest.raises(ModelStoreError):
            name_to_manifest_rel(bad)


def test_embedder_heuristic():
    assert model_store.looks_like_embedder("bge-m3")
    assert model_store.looks_like_embedder("nomic-embed-text:latest")
    assert model_store.looks_like_embedder("hf.co/user/some-embed-model:F16")
    assert not model_store.looks_like_embedder("qwen3:14b")
    assert not model_store.looks_like_embedder("llama3.2:3b")


# ---- store walk -------------------------------------------------------------

def test_list_models_covers_all_registries(tmp_path):
    store = tmp_path / "store"
    _make_model(store, "qwen3:14b", weights=b"W" * 100)
    _make_model(store, "hf.co/user/repo:Q4", weights=b"H" * 50)
    infos = {i.name: i.size_bytes for i in list_models(store)}
    assert set(infos) == {"qwen3:14b", "hf.co/user/repo:Q4"}
    assert infos["qwen3:14b"] > 100  # weights + config blob
    assert list_models(tmp_path / "nowhere") == []


# ---- export -> import round trip --------------------------------------------

def test_export_import_round_trip(tmp_path):
    src, dst = tmp_path / "src", tmp_path / "dst"
    digests = _make_model(src, "qwen3:14b", weights=b"WEIGHTS" * 1000)
    tarball = tmp_path / "qwen3-14b.ollama.tar"

    export_model(src, "qwen3:14b", tarball, _quiet)
    assert tarball.is_file()
    with tarfile.open(tarball) as tar:  # plain (uncompressed) tar, store-relative
        names = set(tar.getnames())
    assert "manifests/registry.ollama.ai/library/qwen3/14b" in names
    assert {f"blobs/{d}" for d in digests} <= names

    imported = import_tarball(tarball, dst, _quiet)
    assert imported == ["qwen3:14b"]
    assert model_present(dst, "qwen3:14b")
    for d in digests:
        assert (dst / "blobs" / d).read_bytes() == (src / "blobs" / d).read_bytes()

    # Re-import dedupes by hash: no error, nothing duplicated.
    assert import_tarball(tarball, dst, _quiet) == ["qwen3:14b"]


def test_reimport_of_present_model_is_a_readonly_noop(tmp_path):
    """Re-importing a model already fully in the store must not write into it
    — the store may be root-owned (the Ollama container chowns it). The
    pre-scan short-circuits before touching anything, so a read-only manifest
    subtree is fine."""
    src, dst = tmp_path / "src", tmp_path / "dst"
    _make_model(src, "qwen3:14b", weights=b"WEIGHTS" * 1000)
    tarball = tmp_path / "qwen3.tar"
    export_model(src, "qwen3:14b", tarball, _quiet)
    assert import_tarball(tarball, dst, _quiet) == ["qwen3:14b"]

    lines = []
    qwen_dir = dst / "blobs"  # freeze the whole store read-only
    for d in (dst, dst / "manifests", dst / "manifests/registry.ollama.ai",
              dst / "manifests/registry.ollama.ai/library",
              dst / "manifests/registry.ollama.ai/library/qwen3", qwen_dir):
        os.chmod(d, 0o555)
    try:
        assert import_tarball(tarball, dst, lines.append) == ["qwen3:14b"]
        assert any("already in the store" in ln for ln in lines)
    finally:
        for d in (dst, dst / "manifests", dst / "manifests/registry.ollama.ai",
                  dst / "manifests/registry.ollama.ai/library",
                  dst / "manifests/registry.ollama.ai/library/qwen3", qwen_dir):
            os.chmod(d, 0o755)


def test_import_of_new_content_into_readonly_store_is_clear(tmp_path):
    """A genuine write into a store owned by another user surfaces an
    actionable ModelStoreError, not a raw errno on a temp path."""
    store = tmp_path / "store"
    # Pre-seed the shared blob so the tar carries only a (new) manifest, and
    # the failure lands on the manifest move, not a blob move.
    shared = b"shared-layer"
    digest = _blob(store, shared)
    manifest = json.dumps({"config": {}, "layers": [
        {"digest": digest.replace("sha256-", "sha256:", 1)}]}).encode()
    tarball = tmp_path / "new.tar"
    with tarfile.open(tarball, "w") as tar:
        _tar_bytes_member(tar, "manifests/registry.ollama.ai/library/newmodel/latest", manifest)
    (store / "manifests").mkdir()
    os.chmod(store / "manifests", 0o555)  # can't create library/newmodel/ under it
    try:
        with pytest.raises(ModelStoreError) as exc:
            import_tarball(tarball, store, _quiet)
        msg = str(exc.value)
        # Verbose, actionable, and literally runnable: the why, the numbered
        # steps, and the store path interpolated into the chown command.
        assert "chown -R" in msg and str(store) in msg
        assert "dffrnt-manager stop" in msg and "models import" in msg
        assert "1." in msg and "2." in msg  # numbered steps survived
    finally:
        os.chmod(store / "manifests", 0o755)


def test_export_refuses_missing_model_and_missing_blob(tmp_path):
    store = tmp_path / "store"
    with pytest.raises(ModelStoreError, match="not in the store"):
        export_model(store, "ghost:latest", tmp_path / "x.tar", _quiet)
    digests = _make_model(store, "qwen3:14b", weights=b"W")
    (store / "blobs" / digests[1]).unlink()
    with pytest.raises(ModelStoreError, match="incomplete"):
        export_model(store, "qwen3:14b", tmp_path / "x.tar", _quiet)


# ---- import guards ----------------------------------------------------------

def _tar_bytes_member(tar, name, data: bytes):
    info = tarfile.TarInfo(name)
    info.size = len(data)
    tar.addfile(info, io.BytesIO(data))


def test_import_rejects_corrupt_blob(tmp_path):
    """A blob whose content doesn't hash to its filename (USB corruption)."""
    store = tmp_path / "store"
    good = b"good-weights"
    digest = f"sha256-{hashlib.sha256(good).hexdigest()}"
    manifest = json.dumps({"config": {}, "layers": [
        {"digest": digest.replace("sha256-", "sha256:", 1)}]}).encode()
    tarball = tmp_path / "corrupt.tar"
    with tarfile.open(tarball, "w") as tar:
        _tar_bytes_member(tar, "manifests/registry.ollama.ai/library/evil/latest", manifest)
        _tar_bytes_member(tar, f"blobs/{digest}", b"EVIL-BYTES")  # wrong content
    with pytest.raises(ModelStoreError, match="checksum mismatch"):
        import_tarball(tarball, store, _quiet)
    assert not model_present(store, "evil:latest")
    assert not list((store / "blobs").glob("*")) if (store / "blobs").is_dir() else True


def test_import_rejects_foreign_members(tmp_path):
    tarball = tmp_path / "stray.tar"
    with tarfile.open(tarball, "w") as tar:
        _tar_bytes_member(tar, "manifests/registry.ollama.ai/library/m/latest", b"{}")
        _tar_bytes_member(tar, "etc/passwd", b"oops")
    with pytest.raises(ModelStoreError, match="unexpected member"):
        import_tarball(tarball, tmp_path / "store", _quiet)


def test_import_rejects_incomplete_archive(tmp_path):
    """Manifest references a blob that's neither in the tar nor the store."""
    missing = f"sha256-{'0' * 64}"
    manifest = json.dumps({"config": {}, "layers": [
        {"digest": missing.replace("sha256-", "sha256:", 1)}]}).encode()
    tarball = tmp_path / "incomplete.tar"
    with tarfile.open(tarball, "w") as tar:
        _tar_bytes_member(tar, "manifests/registry.ollama.ai/library/partial/latest", manifest)
    with pytest.raises(ModelStoreError, match="incomplete"):
        import_tarball(tarball, tmp_path / "store", _quiet)


def test_import_accepts_blob_already_in_store(tmp_path):
    """Completeness may be satisfied by the destination store (shared blobs)."""
    store = tmp_path / "store"
    shared = b"shared-layer"
    digest = _blob(store, shared)
    manifest = json.dumps({"config": {}, "layers": [
        {"digest": digest.replace("sha256-", "sha256:", 1)}]}).encode()
    tarball = tmp_path / "sharing.tar"
    with tarfile.open(tarball, "w") as tar:
        _tar_bytes_member(tar, "manifests/registry.ollama.ai/library/reuse/latest", manifest)
    assert import_tarball(tarball, store, _quiet) == ["reuse:latest"]
    assert model_present(store, "reuse:latest")


# ---- keep file --------------------------------------------------------------

def test_keep_file_round_trip(tmp_path):
    assert model_store.read_keep_file(tmp_path) == []
    model_store.add_to_keep_file(tmp_path, ["qwen3:8b", "hf.co/u/r:Q4"])
    model_store.add_to_keep_file(tmp_path, ["qwen3:8b"])  # dedupes
    assert model_store.read_keep_file(tmp_path) == ["qwen3:8b", "hf.co/u/r:Q4"]
    model_store.remove_from_keep_file(tmp_path, "qwen3:8b")
    assert model_store.read_keep_file(tmp_path) == ["hf.co/u/r:Q4"]
    # Comment lines survive reads without being treated as names.
    assert "#" in (tmp_path / model_store.KEEP_FILE).read_text()


# ---- config.toml surgical rewrite -------------------------------------------

def test_write_config_value_preserves_everything_else(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        "# heading comment\n"
        "gpu = true\n"
        "#llm_model = \"qwen3:4b\" # Lite Model\n"
        "llm_model = \"qwen3:14b\" # Mid-level Model\n"
        "#llm_model = \"qwen3:30b-a3b\" # High-capacity\n"
        "embed_model = \"bge-m3\"\n"
    )
    write_config_value(cfg, "llm_model", "qwen3:8b")
    text = cfg.read_text()
    # New value in place; the stale trailing comment is dropped on purpose.
    assert 'llm_model = "qwen3:8b"\n' in text
    assert "Mid-level" not in text
    # Commented alternatives and every other line survive byte-for-byte.
    assert '#llm_model = "qwen3:4b" # Lite Model' in text
    assert '#llm_model = "qwen3:30b-a3b" # High-capacity' in text
    assert "# heading comment" in text and "gpu = true" in text
    assert 'embed_model = "bge-m3"' in text
    assert text.count("llm_model") == 3  # one live + two commented


def test_write_config_value_appends_missing_key(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text("gpu = false")
    write_config_value(cfg, "llm_model", "qwen3:4b")
    assert cfg.read_text().endswith('llm_model = "qwen3:4b"\n')

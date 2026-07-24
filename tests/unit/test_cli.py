"""installer/cli.py + entry plumbing: parser coverage for every verb the
retired shell scripts provided, the backend/installer factories, and the
frozen-binary app-root anchoring. No docker, no network, no GUI.
"""

import sys
import types
from pathlib import Path

import pytest

from installer.backends import make_backend
from installer.backends.docker_backend import DockerComposeBackend
from installer.backends.portable_backend import PortableBackend
from installer.cli import build_parser
from installer.config import AppConfig, find_app_root
from installer.platform_detect import Pathway


# ---- parser: every retired shell verb has a CLI home ------------------------

@pytest.mark.parametrize("argv,fn_name", [
    (["install"], "_cmd_install"),
    (["install", "bundle.tar.gz", "--dest", "/opt/dffrnt", "--overwrite-config"], "_cmd_install"),
    (["start"], "_cmd_start"),
    (["stop"], "_cmd_stop"),
    (["restart"], "_cmd_restart"),
    (["dev"], "_cmd_dev"),                       # was deploy/start.sh
    (["status"], "_cmd_status"),
    (["logs"], "_cmd_logs"),
    (["logs", "api"], "_cmd_logs"),
    (["audit"], "_cmd_audit"),
    (["reingest", "--dry-run"], "_cmd_reingest"),
    (["reingest", "--yes"], "_cmd_reingest"),
    (["models"], "_cmd_models"),
    (["models", "list"], "_cmd_models"),
    (["models", "pull"], "_cmd_models"),          # was deploy/pull-models.sh
    (["models", "pull", "qwen3:8b"], "_cmd_models"),
    (["models", "use", "qwen3:8b"], "_cmd_models"),
    (["models", "rm", "qwen3:8b"], "_cmd_models"),
    (["models", "export", "qwen3:8b", "/tmp/x.tar"], "_cmd_models"),
    (["models", "import", "/tmp/x.tar"], "_cmd_models"),
])
def test_parser_covers_all_verbs(argv, fn_name):
    args = build_parser().parse_args(argv)
    assert args.fn.__name__ == fn_name


def test_parser_rejects_unknown_command_and_bad_service():
    with pytest.raises(SystemExit):
        build_parser().parse_args(["frobnicate"])
    with pytest.raises(SystemExit):
        build_parser().parse_args(["logs", "nginx"])


def test_export_dest_can_be_positional():
    # run_cli maps the second positional name onto --dest; the parser just
    # has to accept both spellings.
    args = build_parser().parse_args(["models", "export", "qwen3:8b", "out.tar"])
    assert args.names == ["qwen3:8b", "out.tar"]
    args = build_parser().parse_args(["models", "export", "qwen3:8b", "--dest", "out.tar"])
    assert args.dest == "out.tar"


# ---- factories --------------------------------------------------------------

def _config() -> AppConfig:
    return AppConfig(api_port=8000, ollama_url="http://localhost:11434",
                     qdrant_url="http://localhost:6333", gpu=False,
                     llm_model="qwen3:14b", embed_model="bge-m3",
                     audit_log_path="logs/audit.jsonl")


def test_make_backend_picks_pathway(tmp_path):
    container = types.SimpleNamespace(pathway=Pathway.CONTAINER)
    portable = types.SimpleNamespace(pathway=Pathway.PORTABLE)
    assert type(make_backend(tmp_path, _config(), container)) is DockerComposeBackend
    assert type(make_backend(tmp_path, _config(), portable)) is PortableBackend


# ---- frozen app-root anchoring ----------------------------------------------

def test_find_app_root_frozen_uses_executable_dir(tmp_path, monkeypatch):
    """A one-file binary must anchor on sys.executable — __file__ points
    into the transient extraction dir. Bundle layout: compose file sits
    next to the binary."""
    (tmp_path / "docker-compose.yml").write_text("services: {}\n")
    exe = tmp_path / "dffrnt-manager"
    exe.write_bytes(b"")
    monkeypatch.delenv("DFFRNT_APP_ROOT", raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    assert find_app_root() == tmp_path


def test_find_app_root_env_override_beats_frozen(tmp_path, monkeypatch):
    monkeypatch.setenv("DFFRNT_APP_ROOT", str(tmp_path / "elsewhere"))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert find_app_root() == tmp_path / "elsewhere"

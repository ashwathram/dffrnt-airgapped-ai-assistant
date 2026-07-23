"""Headless command-line interface — the same backends the GUI drives,
minus Tk, so an SSH'd or displayless box (AWS targets, CI) has full
install/manage/model coverage from the one shipped binary:

    dffrnt-manager                    # no args: the GUI control panel
    dffrnt-manager install [bundle]   # deploy a dffrnt-*.tar.gz
    dffrnt-manager start|stop|restart|status
    dffrnt-manager logs [service]     # follow (Ctrl-C to stop)
    dffrnt-manager audit              # follow the app audit trail
    dffrnt-manager reingest [--dry-run] [--yes]
    dffrnt-manager dev                # dev loop: qdrant+ollama only
    dffrnt-manager models [list]
    dffrnt-manager models pull|rm|use NAME
    dffrnt-manager models export NAME DEST.tar
    dffrnt-manager models import TARBALL

This module must stay import-clean of tkinter: a server's Python may not
have Tk at all, and the CLI is exactly for those machines. Views and app.py
are imported by __main__ only on the bare-launch (GUI) path.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import model_store
from .backends import Backend, BackendError, make_backend
from .config import AppConfig, find_app_root, find_config, load_config, write_config_value
from .installers import InstallError, find_bundles, make_installer
from .installers.docker_installer import default_install_dest
from .logging_setup import configure_logging
from .platform_detect import detect


def _echo(line: str) -> None:
    print(line, flush=True)


class _Context:
    """Everything a command needs, resolved once: app root, config,
    platform, backend — the same resolution order app.py performs."""

    def __init__(self):
        self.platform_info = detect()
        self.app_root = find_app_root()
        configure_logging(self.app_root)
        self.reload()

    def reload(self) -> None:
        self.config: AppConfig = load_config(self.app_root)
        self.backend: Backend = make_backend(self.app_root, self.config, self.platform_info)


# ---- commands ---------------------------------------------------------------

def _cmd_install(ctx: _Context, args) -> int:
    installer = make_installer(ctx.platform_info)

    checks = installer.check_prerequisites()
    for check in checks:
        _echo(f"   [{'OK' if check.ok else 'MISSING'}] {check.name}"
              + (f" — {check.detail}" if check.detail else ""))
    if not all(c.ok for c in checks):
        _echo("!! Missing prerequisites (see above). Install them and re-run.")
        return 1

    bundle = Path(args.bundle) if args.bundle else None
    if bundle is None:
        exe_dir = Path(sys.executable).parent if getattr(sys, "frozen", False) \
            else Path.cwd()
        candidates = find_bundles([exe_dir, Path.cwd(), Path.cwd() / "dist",
                                   ctx.app_root, ctx.app_root.parent])
        if len(candidates) != 1:
            _echo(f"!! Expected exactly one dffrnt-*.tar.gz near the manager "
                  f"(found {len(candidates)}). Pass the bundle path explicitly.")
            return 1
        bundle = candidates[0]

    dest = Path(args.dest) if args.dest else default_install_dest()
    info = installer.inspect_bundle(bundle)
    _echo(f">> {info.path.name} — {info.target_system} bundle, "
          f"{model_store.human_size(info.size_bytes)} -> {dest}")

    keep_config = True
    if (dest / "config.toml").is_file():
        keep_config = not args.overwrite_config
        _echo("   existing config.toml will be "
              + ("overwritten (archived as config.toml.old)" if not keep_config
                 else "kept (pass --overwrite-config for the bundle default)"))

    installer.install(bundle, dest, _echo, keep_config=keep_config)
    _echo(f">> Manage it from here on with: {sys.argv[0]} status|stop|restart|logs")
    return 0


def _cmd_start(ctx: _Context, args) -> int:
    ctx.backend.start(_echo)
    return 0


def _cmd_stop(ctx: _Context, args) -> int:
    ctx.backend.stop(_echo)
    return 0


def _cmd_restart(ctx: _Context, args) -> int:
    ctx.backend.restart(_echo)
    return 0


def _cmd_dev(ctx: _Context, args) -> int:
    ctx.backend.start_dev(_echo)
    return 0


def _cmd_status(ctx: _Context, args) -> int:
    worst = 0
    for svc in ctx.backend.status():
        state = svc.detail or ("up" if svc.running else "down")
        _echo(f"   {svc.name:<8} {state}")
        if not svc.running or svc.healthy is False:
            worst = 1
    if worst == 0:
        _echo(f">> UI: http://localhost:{ctx.config.api_port}")
    return worst


def _cmd_logs(ctx: _Context, args) -> int:
    service = None if args.service in (None, "all") else args.service
    follower = ctx.backend.stream_logs(service, _echo)
    try:
        while True:
            lines, ended = follower.drain()
            for line in lines:
                _echo(line)
            if ended:
                _echo("-- log stream ended --")
                return 0
            time.sleep(0.2)
    except KeyboardInterrupt:
        return 0
    finally:
        follower.stop()


def _cmd_audit(ctx: _Context, args) -> int:
    """Follow logs/audit.jsonl, pretty-printing each JSON record — the
    audit trail is a host-side bind mount, so no container is needed."""
    path = ctx.app_root / ctx.config.audit_log_path
    if not path.is_file():
        _echo(f"!! No audit log at {path} yet (has the app been used?).")
        return 1
    _echo(f">> Following {path} (Ctrl-C to stop)")

    def show(raw: str) -> None:
        raw = raw.strip()
        if not raw:
            return
        try:
            _echo(json.dumps(json.loads(raw), indent=2))
        except ValueError:
            _echo(raw)  # partial/non-JSON line: never abort the stream

    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh.readlines()[-50:]:
                show(line)
            while True:
                line = fh.readline()
                if line:
                    show(line)
                else:
                    time.sleep(0.5)
    except KeyboardInterrupt:
        return 0


def _cmd_reingest(ctx: _Context, args) -> int:
    ctx.backend.reingest_preview(_echo)
    if args.dry_run:
        return 0
    # Confirm when interactive; non-interactive proceeds so automation works
    # (same contract the retired shell control panel had).
    if sys.stdin.isatty() and not args.yes:
        answer = input(">> Proceed with re-ingestion of the files listed above? [y/N] ")
        if answer.strip().lower() not in ("y", "yes"):
            _echo(">> Aborted — nothing changed.")
            return 0
    ctx.backend.reingest_apply(_echo)
    return 0


def _cmd_models(ctx: _Context, args) -> int:
    action = args.action or "list"

    if action == "list":
        infos = ctx.backend.list_models()
        if not infos:
            _echo("   (no models in the store)")
            return 0
        llm = model_store.with_tag(ctx.config.llm_model) if ctx.config.llm_model else ""
        embed = model_store.with_tag(ctx.config.embed_model) if ctx.config.embed_model else ""
        kept = {model_store.with_tag(n) for n in model_store.read_keep_file(ctx.app_root)}
        for info in infos:
            role = ("LLM" if info.name == llm else
                    "embedder" if info.name == embed else
                    "imported" if info.name in kept else
                    "prunes on restart")
            _echo(f"   {info.name:<40} {model_store.human_size(info.size_bytes):>10}  {role}")
        return 0

    if action == "pull":
        names = args.names or [m for m in (ctx.config.llm_model, ctx.config.embed_model) if m]
        for name in names:
            ctx.backend.pull_model(_echo, name)
        return 0

    if action == "rm":
        name = _one_name(args)
        active = {model_store.with_tag(m) for m in
                  (ctx.config.llm_model, ctx.config.embed_model) if m}
        if model_store.with_tag(name) in active:
            _echo(f"!! {name} is the active LLM or embedder — switch first, then remove.")
            return 1
        ctx.backend.delete_model(_echo, name)
        return 0

    if action == "export":
        name = _one_name(args)
        if not args.dest:
            _echo("!! models export needs a destination: models export NAME DEST.tar")
            return 1
        ctx.backend.export_model(_echo, name, Path(args.dest))
        return 0

    if action == "import":
        tar = _one_name(args)  # positionally the tarball path
        ctx.backend.import_model_tar(_echo, Path(tar))
        _echo(">> Activate it with: models use <name>")
        return 0

    if action == "use":
        return _models_use(ctx, _one_name(args))

    _echo(f"!! Unknown models action '{action}' "
          "(list, pull, rm, use, export, import)")
    return 2


def _one_name(args) -> str:
    if not args.names:
        raise BackendError("this models action needs a model name/path argument")
    return args.names[0]


def _models_use(ctx: _Context, name: str) -> int:
    """Swap the active LLM: rewrite config.toml, then restart so start's
    ensure/prune loads the new model and reclaims the old one — the CLI
    twin of the GUI's Apply & restart (views/models.py)."""
    model_store.name_to_manifest_rel(name)  # syntax check; raises on garbage
    config_path = find_config(ctx.app_root)
    if config_path is None:
        _echo(f"!! No config.toml under {ctx.app_root} — is the stack installed?")
        return 1
    if model_store.with_tag(name) == model_store.with_tag(ctx.config.llm_model or "-"):
        _echo(f">> {name} is already the active LLM.")
        return 0
    offline = getattr(ctx.backend, "target_system", "online") == "offline"
    present = model_store.model_present(ctx.backend.models_dir, name)
    if offline and not present:
        _echo(f"!! '{name}' is not in this machine's store, and an offline "
              "deployment cannot pull. Import it first: models import <tarball>")
        return 1
    if not present:
        _echo(f">> {name} is not cached yet — it will be pulled during the restart.")
    write_config_value(config_path, "llm_model", name)
    _echo(f">> config.toml: llm_model = \"{name}\"")
    model_store.remove_from_keep_file(ctx.app_root, name)
    ctx.reload()  # fresh AppConfig + backend so ensure/prune see the new model
    ctx.backend.restart(_echo)
    return 0


# ---- parser / entry ---------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dffrnt-manager",
        description="DFFRNT AI Assistant control panel. Run with no arguments "
                    "for the GUI; any command below runs headless.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("install", help="deploy a dffrnt-*.tar.gz bundle")
    p.add_argument("bundle", nargs="?", help="bundle path (auto-detected if omitted)")
    p.add_argument("--dest", help="install destination (default: ./dffrnt)")
    p.add_argument("--overwrite-config", action="store_true",
                   help="replace an existing config.toml with the bundle default "
                        "(default: keep; the old file is archived)")
    p.set_defaults(fn=_cmd_install)

    for name, fn, doc in (
        ("start", _cmd_start, "bring the whole stack up"),
        ("stop", _cmd_stop, "stop all services"),
        ("restart", _cmd_restart, "stop then start"),
        ("dev", _cmd_dev, "dev loop: qdrant + ollama only, API on the host"),
        ("status", _cmd_status, "service + API health (exit 1 if degraded)"),
        ("audit", _cmd_audit, "follow the app audit trail (logs/audit.jsonl)"),
    ):
        sub.add_parser(name, help=doc).set_defaults(fn=fn)

    p = sub.add_parser("logs", help="follow service logs (Ctrl-C to stop)")
    p.add_argument("service", nargs="?", choices=["all", "qdrant", "ollama", "api"])
    p.set_defaults(fn=_cmd_logs)

    p = sub.add_parser("reingest", help="force re-ingest every stored document")
    p.add_argument("--dry-run", action="store_true", help="preview only")
    p.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    p.set_defaults(fn=_cmd_reingest)

    p = sub.add_parser("models",
                       help="list | pull [NAME...] | rm NAME | use NAME | "
                            "export NAME DEST.tar | import TARBALL")
    p.add_argument("action", nargs="?",
                   choices=["list", "pull", "rm", "use", "export", "import"])
    p.add_argument("names", nargs="*", metavar="NAME",
                   help="model name(s) or, for import, a tarball path")
    p.add_argument("--dest", help="(export) destination tar path — or pass it "
                                  "as the second positional argument")
    p.set_defaults(fn=_cmd_models)

    return parser


def run_cli(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    # `models export NAME DEST` positional convenience: second name is the dest.
    if getattr(args, "action", None) == "export" and not getattr(args, "dest", None) \
            and len(getattr(args, "names", [])) > 1:
        args.dest = args.names[1]
    try:
        ctx = _Context()
        return args.fn(ctx, args)
    except (BackendError, InstallError, model_store.ModelStoreError) as exc:
        _echo(f"!! {exc}")
        return 1
    except KeyboardInterrupt:
        return 130

# DFFRNT Control Panel (desktop GUI)

A Tkinter desktop app that replaces the day-to-day parts of
[`deploy/dffrnt_ctrl_panel.sh`](../deploy/dffrnt_ctrl_panel.sh) — start,
stop, restart, status, logs, reingest — with a GUI that runs unchanged on
Linux, Windows, and (once phase 2 lands) macOS. Tkinter ships with Python
itself, so this adds no dependency and freezes cleanly for air-gapped
delivery.

**Status: preliminary.** The container pathway (Linux/Windows) is
implemented and exercised against a real `docker compose` stack. The
`install-prerequisites.sh` / `install.sh` bundle-unpack flow is not — this
app currently manages an *already-installed* stack, same scope as
`dffrnt_ctrl_panel.sh` itself.

## Running it

Use the project's `uv`-managed `.venv`, not a system Python:

```bash
uv run python -m installer          # from the repo root
```

On Linux, Tkinter needs the OS's Tk library, which isn't a `pip`/`uv`
package — install your distro's `tk` (Arch: `tk`, Debian/Ubuntu:
`python3-tk`) if `import tkinter` fails. Windows/macOS python.org
installers already bundle Tcl/Tk, so this only comes up on Linux dev boxes.

It auto-detects the app root the same way `dffrnt_ctrl_panel.sh` does: a
sibling `deploy/` directory in a dev checkout, or the directory it's
running from in an installed bundle (override with `DFFRNT_APP_ROOT`).
`config.toml` resolution follows the same rule as `DFFRNT_CONFIG`.

## Reingest

The Dashboard's "Reingest documents" button mirrors
`dffrnt_ctrl_panel.sh reingest` exactly, including its safety order:

1. Runs `--dry-run` inside the API container and streams the reconciliation
   preview (what would change) into the console. Nothing is mutated yet.
2. On a clean preview, a confirm dialog asks the operator to proceed.
3. Only on "yes" does it run the real `--force --verbose` reingest.

Declining, or the API container not running (checked up front, same as the
bash script's guard), aborts with nothing changed. See
`Backend.reingest_preview` / `Backend.reingest_apply` in
`backends/__init__.py` and their implementation in `docker_backend.py`.

## Logging

Every lifecycle operation — `start`, `stop`, `restart` (via `start`/`stop`),
`check_prerequisites`, `reingest_preview`, `reingest_apply` — writes its
full output plus a begin/end/error marker to `<app_root>/logs/installer.log`
(falls back to the OS temp dir if that path isn't writable), in addition to
whatever's shown live in the GUI console. This is the same `logs/`
directory `dffrnt_ctrl_panel.sh`/the API already use for `audit.jsonl`. The
app logs its own startup context too — detected platform, resolved config,
and which backend it picked — so a support request can start from the log
file alone.

**Deliberately not logged**: `status()` polling and `stream_logs()`
follow output. Both are read-only "management" queries, not operations —
status is re-run after every action and on a timer, and log-follow output
is just Docker's own container logs, which Docker already persists. Logging
either to our file would add an unbounded amount of noise for information
that's already live in the GUI or already durable elsewhere. See
`logging_setup.py`'s module docstring and the comment above `status()` /
`stream_logs()` in `docker_backend.py` for the reasoning in place.

## Why two pathways

```
Linux / Windows -> Pathway.CONTAINER -> DockerComposeBackend  (implemented)
macOS           -> Pathway.PORTABLE  -> PortableBackend       (stub, phase 2)
```

Docker Desktop on macOS runs containers inside a Linux VM with no
Metal/GPU passthrough, so a containerized Ollama on a Mac would be
CPU-only — a non-starter for this app's LLM/embedding workload. The
planned fix (see
[`backends/portable_backend.py`](backends/portable_backend.py)) is to
carry portable, self-contained binaries in the macOS bundle instead:
Ollama as a native host process for full GPU acceleration, plus a bundled
portable container runtime for Qdrant (which is CPU-only and doesn't need
the native path).

`platform_detect.detect()` picks the pathway; `app.py` picks the backend
class from it. Everything else — both views, the widget helpers, the
BackgroundJob/LogFollower plumbing — talks only to the `Backend` ABC in
`backends/__init__.py`, so implementing `PortableBackend` later is a
self-contained change that shouldn't need to touch the GUI layer at all.

## Layout

```
installer/
  app.py                  Tk root window, sidebar nav, backend selection, startup logging
  theme.py                Palette/fonts ported from dffrnt_assistant/ui/styles/*.css
  platform_detect.py      OS/arch/GPU detection, the Pathway enum
  config.py               config.toml + app-root resolution (mirrors cfg() in the bash script)
  logging_setup.py        installer.log file handler + the with_logging() output-tap helper
  process.py              subprocess streaming + the BackgroundJob/LogFollower thread bridge
  widgets.py               small styled-widget factories (buttons, status pills, console)
  backends/
    __init__.py            Backend ABC + PrereqCheck/ServiceStatus/BackendError
    docker_backend.py       CONTAINER pathway — ports dffrnt_ctrl_panel.sh verb for verb
    portable_backend.py     PORTABLE pathway — documented stub, not implemented
  views/
    dashboard.py            platform info, prereqs, service status, start/stop/restart/reingest
    logs.py                  service picker + follow/stop streaming logs
  assets/icon.png           window icon, generated from ui/img/dffrnt_favicon.jpg
```

## Design language

Ported from `dffrnt_assistant/ui/styles/theme.css`'s custom properties —
same navy sidebar (`#091A29`), light content area, primary/ghost/danger
buttons, and status colors (green/red/amber) as the web UI's document
library. ttk has no border-radius or box-shadow, so cards are flat
rectangles rather than the web UI's rounded ones; everything else in the
palette carries over directly. See `theme.COLORS` / `theme.STATUS_COLORS`
for the token source of truth.

## What isn't here yet

- The macOS `PortableBackend` (see above) — all of its methods, including
  reingest, still raise `NotImplementedError` (logged as a warning each
  time, so an attempt on an unsupported Mac leaves a trace).
- The `install.sh`/`install-prerequisites.sh` first-run flow (bundle
  unpack, Docker/driver provisioning) — this app assumes Docker and the
  stack are already installed, same as `dffrnt_ctrl_panel.sh`.
- Packaging as a native app (PyInstaller/py2app/etc.) for distribution
  without a Python install on the target machine.

## Manual verification done so far

This sandbox has no working Tk display (`libtk8.6.so` missing, and
installing it was out of scope here), so the GUI itself hasn't been
visually verified — only exercised at the logic layer:

- `platform_detect.detect()` and `config.load_config()` against this repo's
  real `deploy/` and `config.toml`.
- `DockerComposeBackend.check_prerequisites()` / `.status()` against the
  real Docker daemon on this machine (correctly reports the daemon as
  unreachable here, and all three services as not running).
- `DockerComposeBackend.reingest_preview()` against the real daemon with no
  API container running — correctly raises `BackendError` through the
  `_require_api_running` guard, and the failure is both logged (with
  traceback, to `installer.log`) and surfaced as `job.error`.
- `process.BackgroundJob` success and failure paths (`echo` / `false`).
- `PortableBackend`'s stub behavior (`NotImplementedError`, prereq/status
  messaging, and that every attempted operation logs a warning first).
- `logging_setup.configure_logging()`'s file output, inspected directly
  after the runs above — correct levels (prereq failures as WARNING,
  lifecycle brackets as INFO, exceptions as ERROR with traceback).
- `py_compile` + `ast.parse` on every module.

**Before relying on this**, run it on a machine with a real display and
click through: Start (full cold-start including model pull/prune), Stop,
Restart, Status refresh, Logs follow/stop, and Reingest (both declining and
confirming the prompt, and with the stack stopped to see the "not running"
guard) — on both a `gpu = false` and `gpu = true` config.

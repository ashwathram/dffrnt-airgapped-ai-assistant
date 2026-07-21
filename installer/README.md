# DFFRNT Control Panel (desktop GUI)

A Tkinter desktop app with three tabs:

- **Install** — first-run deployment from a `dffrnt-*.tar.gz` bundle,
  porting [`deploy/install.sh`](../deploy/install.sh): pick bundle + dest,
  prereq gate, unpack (stdlib `tarfile`, so no `tar` binary needed —
  works on Windows too), `docker load`, first start.
- **Manage** — day-to-day lifecycle, porting
  [`deploy/dffrnt_ctrl_panel.sh`](../deploy/dffrnt_ctrl_panel.sh): start,
  stop, restart, status, reingest.
- **Logs** — follow container logs per service.

Runs unchanged on Linux, Windows, and macOS. Tkinter ships with Python
itself, so this adds no dependency and freezes cleanly for air-gapped
delivery.

**Status: preliminary.** The container pathway (Linux/Windows) is
implemented; management verified against a real `docker compose` stack and
the install unpack logic against a synthetic bundle. The portable pathway
(macOS: native Ollama with Metal + colima-hosted containers) is implemented
and logic-tested on this Linux box with a faked runtime — it has NOT yet
run on actual macOS hardware. `install-prerequisites.sh` (Docker/NVIDIA
host provisioning on Linux) remains out of scope — the Install tab's prereq
gate tells you what's missing but doesn't install it.

**Shipping caveat for the Install tab:** a GUI that installs the bundle
cannot itself live inside that bundle. For install-from-scratch on a target
machine, this app must ship in `dist/` *next to* the tarball (like
`install.sh` does) — and since targets are only guaranteed to have Docker,
that realistically means freezing it (PyInstaller) into a self-contained
binary. Until that's wired into `package.sh`, the Install tab is usable
from a dev checkout (installing/updating a local deployment from a locally
packaged `dist/`).

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
Linux / Windows -> Pathway.CONTAINER -> DockerComposeBackend / DockerInstaller
macOS           -> Pathway.PORTABLE  -> PortableBackend / PortableInstaller
```

Docker's Linux VM has no Metal/GPU passthrough, so a containerized Ollama
on a Mac would be CPU-only — a non-starter for this app's LLM/embedding
workload. The portable pathway therefore runs **Ollama as a native host
process** (Metal is automatic on Apple Silicon; keeping it out of the VM
is the entirety of "enabling Metal") with the same tuning env as the
compose service, while **Qdrant + the API stay containers** under a
bundled portable runtime: colima + lima + the static docker CLI + compose
plugin, all vendored in `dist/portable/macos/` by
`deploy/package-macos-portable.sh` — nothing installed system-wide, and
all runtime state (COLIMA_HOME/LIMA_HOME/DOCKER_CONFIG) contained under
the install's `portable/` directory. The API container reaches the native
Ollama via `host.docker.internal` (compose stdin override with
`depends_on: !override` to drop the never-started ollama container).

The portable classes subclass the container ones at explicit seams
(`_env`, `_ollama_cmd`, `_preflight`, `_compose_up`,
`_manifest_model_names`; installer: `_backend_for`, `_post_unpack`,
`_image_tars`, `_load_env`), so the lifecycle flow, model ensure/prune,
health waits, and reingest are single-sourced — and the GUI layer needed
no changes at all.

**Air-gap caveat (macOS only):** colima's *first* start downloads its VM
guest image. Warm it on a networked Mac before transferring `dist/`, or
allow one-time network access at install. Everything else (models, images,
binaries) is fully offline. See `package-macos-portable.sh`'s header.

## Layout

```
installer/
  app.py                  Tk root window, Install/Manage/Logs nav, post-install re-point
  theme.py                Palette/fonts ported from dffrnt_assistant/ui/styles/*.css
  platform_detect.py      OS/arch/GPU detection, the Pathway enum
  config.py               config.toml / bundle.conf / app-root resolution
  logging_setup.py        installer.log file handler + the with_logging() output-tap helper
  process.py              subprocess streaming + the BackgroundJob/LogFollower thread bridge
  widgets.py               styled-widget factories + the ScrollableFrame container
  backends/
    __init__.py            Backend ABC + PrereqCheck/ServiceStatus/BackendError
    docker_backend.py       CONTAINER pathway — ports dffrnt_ctrl_panel.sh verb for verb
    portable_backend.py     PORTABLE pathway — native Metal Ollama + colima containers
  installers/
    __init__.py            Installer ABC + BundleInfo/InstallError + find_bundles()
    docker_installer.py     CONTAINER pathway — ports install.sh stage for stage
    portable_installer.py   PORTABLE pathway — + runtime staging, skips the ollama image
  views/
    install.py              bundle picker, dest, prereq gate, install + streamed console
    dashboard.py            the Manage tab: prereqs, service status, start/stop/restart/reingest
    logs.py                  service picker + follow/stop streaming logs
  assets/icon.png           window icon, generated from ui/img/dffrnt_favicon.jpg
```

Views scroll (`widgets.ScrollableFrame`) when content exceeds the window,
with the mouse wheel routed to whichever tab is visible. The app opens on
Manage when an installed stack is detected, otherwise on Install; a
successful install re-points Manage/Logs at the new app root in place.

## Design language

Ported from `dffrnt_assistant/ui/styles/theme.css`'s custom properties —
same navy sidebar (`#091A29`), light content area, primary/ghost/danger
buttons, and status colors (green/red/amber) as the web UI's document
library. ttk has no border-radius or box-shadow, so cards are flat
rectangles rather than the web UI's rounded ones; everything else in the
palette carries over directly. See `theme.COLORS` / `theme.STATUS_COLORS`
for the token source of truth.

## What isn't here yet

- **On-Mac validation of the portable pathway.** All macOS logic was
  exercised on Linux with a faked runtime; colima's first boot, the
  host.docker.internal route from the VM, Metal inference, and the full
  install flow need a real Apple Silicon machine (see the checklist below).
- `install-prerequisites.sh`'s job (Docker Engine / NVIDIA driver + toolkit
  provisioning on Linux) — inherently privileged, OS-specific host
  mutation; the Install tab's prereq gate reports what's missing instead.
- Packaging as a native app (PyInstaller/py2app/etc.) and wiring it into
  `package.sh`'s `dist/` output — required before the Install tab can serve
  a bare target machine (see the shipping caveat at the top). On macOS the
  target additionally needs a Python with Tk until the GUI is frozen.
- Offline seeding of colima's guest image (see the air-gap caveat above).

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
- `PortableBackend` / `PortableInstaller` against a faked runtime (shell
  scripts standing in for ollama/docker/colima/limactl): `_env`
  containment (PATH, DOCKER_HOST, COLIMA_HOME/LIMA_HOME/DOCKER_CONFIG,
  CLI-vs-serve OLLAMA_HOST split), manifest walking of a host-side model
  store including a stale manifest, prereq reporting (incl. the Apple
  Silicon/Metal line), status degradation when docker is unreachable,
  `find_portable_runtime` discovery from a dist layout, and the image
  filter keeping app+qdrant while skipping the ollama container image.
- The macOS compose stdin override validated against real `docker compose
  config`: `depends_on: !override` correctly drops the ollama dependency
  while keeping qdrant's health condition (this test caught that `!reset`
  silently unsets the whole node — a real bug fixed before shipping),
  OLLAMA_URL re-pointed at host.docker.internal, extra_hosts host-gateway
  applied.
- `logging_setup.configure_logging()`'s file output, inspected directly
  after the runs above — correct levels (prereq failures as WARNING,
  lifecycle brackets as INFO, exceptions as ERROR with traceback).
- `py_compile` + `ast.parse` on every module.

- Install-tab logic without a display: bundle auto-discovery
  (`find_bundles`), `inspect_bundle` on a valid synthetic bundle (reads
  TARGET_SYSTEM) and on garbage (clean `InstallError`), and the
  strip-components-1 unpack with operator-config preservation.

**Before relying on this**, run it on a machine with a real display and
click through: Start (full cold-start including model pull/prune), Stop,
Restart, Status refresh, Logs follow/stop (including switching the service
dropdown mid-follow), Reingest (both declining and confirming the prompt,
and with the stack stopped to see the "not running" guard), scrolling each
tab at a small window size, and a full Install from a real `package.sh`
bundle (fresh dest + update-in-place with an edited config.toml) — on both
a `gpu = false` and `gpu = true` config.

**macOS checklist** (Apple Silicon, from a dist/ built by the "Package:
macOS deployment" job): Install from scratch (runtime staging, colima
first boot, image load skipping the ollama tar, first start); confirm
Metal via the ollama-native.log (`gpu` layers / Metal lines) and that
query latency matches native expectations; confirm the API container
answers queries (i.e. host.docker.internal reaches the host Ollama);
Stop/Start cycle (colima stop/start, native process pidfile); the Logs
tab's "ollama" selection tailing the native log; and Reingest end-to-end.

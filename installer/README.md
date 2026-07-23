# DFFRNT Control Panel (installer/manager)

The single management surface for the stack — there are no shell scripts on
targets anymore (only the two packaging scripts remain in `deploy/`, and
they run on the build machine). One codebase, two faces:

- **GUI** (launch with no arguments): a Tkinter app with four tabs —
  **Install** (first-run deployment from a `dffrnt-*.tar.gz` bundle: pick
  bundle + dest, prereq gate, unpack via stdlib `tarfile`, `docker load`,
  first start), **Manage** (start/stop/restart, status, reingest),
  **Models** (switch the active LLM; move models on/off an air-gapped
  machine as tarballs — see below), **Logs** (follow container logs).
- **CLI** (`cli.py`, any argument): the same verbs headless —
  `install`, `start`, `stop`, `restart`, `status`, `logs`, `audit`,
  `reingest`, `dev`, `models list|pull|rm|use|export|import` — for SSH'd
  or displayless boxes (AWS targets). The CLI never imports tkinter.

Runs unchanged on Linux, Windows, and macOS. Tkinter ships with Python
itself, so this adds no third-party runtime dependency.

**Shipping:** `deploy/package.sh` freezes this package (PyInstaller, the
`package` dependency group) into a self-contained `dffrnt-manager` binary
and ships it twice: next to the tarball in `dist/` (bootstrap install on a
box that has only Docker) and inside the bundle (managing the installed
stack from the app root). The binary is platform-specific — package on a
machine matching the target, like the container images. macOS currently
ships the package as *source* instead (`python3 -m installer`) until
freezing is exercised on real Apple hardware.

**Status: preliminary.** The container pathway (Linux/Windows) is
implemented; management verified against a real `docker compose` stack and
the install unpack logic against a synthetic bundle. The portable pathway
(macOS: native Ollama with Metal + colima-hosted containers) is implemented
and logic-tested on a Linux box with a faked runtime — it has NOT yet run
on actual macOS hardware. Host provisioning (Docker Engine / NVIDIA driver
+ Container Toolkit) is out of scope — the prereq gates tell you exactly
what's missing but don't install it.

## Running it

Use the project's `uv`-managed `.venv`, not a system Python:

```bash
uv run python -m installer          # from the repo root
```

On Linux, Tkinter needs the OS's Tk library, which isn't a `pip`/`uv`
package — install your distro's `tk` (Arch: `tk`, Debian/Ubuntu:
`python3-tk`) if `import tkinter` fails. Windows/macOS python.org
installers already bundle Tcl/Tk, so this only comes up on Linux dev boxes.

It auto-detects the app root: a
sibling `deploy/` directory in a dev checkout, or the directory it's
running from in an installed bundle (override with `DFFRNT_APP_ROOT`).
`config.toml` resolution follows the same rule as `DFFRNT_CONFIG`.

## The Models tab (offline model transfer + switching)

Everything the runtime consumes is Ollama's store format — a
`manifests/<registry>/…/<name>/<tag>` JSON index plus content-addressed
`blobs/sha256-*` — living host-side in `<app_root>/ollama_models` on every
pathway (bind-mounted into the container on Linux/Windows, `OLLAMA_MODELS`
for the native macOS process). The Models tab operates on that directory
directly (`model_store.py`), so listing/import/export work with the stack
down; only pull and delete talk to the serving Ollama.

**Getting a model onto an air-gapped machine:**

1. On the **networked staging machine**: Models → Export — pick an
   installed model or type any Ollama name (it's pulled first if absent),
   choose a file on the USB drive. One uncompressed `.tar` of the manifest
   + blobs (weights are already quantized; gzip would burn minutes for
   ~1%). Exporting refuses up front if the drive is FAT32 and the model
   exceeds its 4 GiB single-file ceiling — use exFAT.
2. On the **air-gapped machine**: Models → Import — every blob is
   sha256-verified against its filename before anything touches the store
   (catches USB corruption), manifests are checked for completeness, and
   blobs dedupe by hash.
3. Select it under **Active model** → Apply & restart. This rewrites
   `llm_model` in `config.toml` (surgically — the file's comments survive)
   and restarts the stack; start's ensure/prune loads the new model and
   reclaims the old one's disk.

**The prune interaction:** start-time pruning removes every cached model
the live config doesn't reference — right for reclaiming disk on a swap,
wrong for a model just imported but not yet selected. Imported models are
therefore recorded in `<app_root>/models.keep` and protected from the
sweep (GUI and CLI alike) until they become the
active model or are deleted from the Installed list.

Switching is **LLM-only** by design: changing `embed_model` changes the
vector dimension and demands a full re-ingest of every document, so it
stays a deliberate `config.toml` edit.

A raw HuggingFace download is *not* importable as-is: a safetensors repo
needs a llama.cpp convert + quantize first, and a GGUF file needs one
`ollama create` on any Ollama machine — after either, it's in a store and
exportable from this tab. `hf.co/...` pulls land under their own registry
namespace, which the store walk covers.

## Reingest

The Dashboard's "Reingest documents" button (and the CLI's `reingest`)
follow a strict safety order:

1. Runs `--dry-run` inside the API container and streams the reconciliation
   preview (what would change) into the console. Nothing is mutated yet.
2. On a clean preview, a confirm dialog asks the operator to proceed.
3. Only on "yes" does it run the real `--force --verbose` reingest.

Declining, or the API container not running (checked up front), aborts
with nothing changed. See
`Backend.reingest_preview` / `Backend.reingest_apply` in
`backends/__init__.py` and their implementation in `docker_backend.py`.

## Logging

Every lifecycle operation — `start`, `stop`, `restart` (via `start`/`stop`),
`check_prerequisites`, `reingest_preview`, `reingest_apply` — writes its
full output plus a begin/end/error marker to `<app_root>/logs/installer.log`
(falls back to the OS temp dir if that path isn't writable), in addition to
whatever's shown live in the GUI console. This is the same `logs/`
directory the API already uses for `audit.jsonl`. The
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
(`_env`, `_ollama_cmd`, `_preflight`, `_compose_up`; installer:
`_backend_for`, `_post_unpack`, `_image_tars`, `_load_env`), so the
lifecycle flow, model ensure/prune/store operations, health waits, and
reingest are single-sourced — and the GUI layer needed no changes at all.

**Air-gap caveat (macOS only):** colima's *first* start downloads its VM
guest image. Warm it on a networked Mac before transferring `dist/`, or
allow one-time network access at install. Everything else (models, images,
binaries) is fully offline. See `package-macos-portable.sh`'s header.

## Layout

```
installer/
  app.py                  Tk root window, Install/Manage/Models/Logs nav, re-point logic
  cli.py                  headless CLI over the same backends (no tkinter import)
  model_store.py          Ollama store walk, tarball export/import, models.keep
  theme.py                Palette/fonts ported from dffrnt_assistant/ui/styles/*.css
  platform_detect.py      OS/arch/GPU detection, the Pathway enum
  config.py               config.toml / bundle.conf / app-root resolution
  logging_setup.py        installer.log file handler + the with_logging() output-tap helper
  process.py              subprocess streaming + the BackgroundJob/LogFollower thread bridge
  widgets.py               styled-widget factories + the ScrollableFrame container
  backends/
    __init__.py            Backend ABC + PrereqCheck/ServiceStatus/BackendError
    docker_backend.py       CONTAINER pathway — compose lifecycle + model ensure/prune
    portable_backend.py     PORTABLE pathway — native Metal Ollama + colima containers
  installers/
    __init__.py            Installer ABC + BundleInfo/InstallError + find_bundles()
    docker_installer.py     CONTAINER pathway — unpack, image load, first start
    portable_installer.py   PORTABLE pathway — + runtime staging, skips the ollama image
  views/
    install.py              bundle picker, dest, prereq gate, install + streamed console
    dashboard.py            the Manage tab: prereqs, service status, start/stop/restart/reingest
    logs.py                  service picker + follow/stop streaming logs
    models.py                the Models tab: swap/import/export/delete
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
- Host provisioning (Docker Engine / NVIDIA driver + toolkit on Linux) —
  inherently privileged, OS-specific host mutation; the prereq gates
  report what's missing instead.
- Freezing on macOS (py2app or PyInstaller-on-Mac) — until then the macOS
  dist ships this package as source and the target needs a Python with Tk.
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

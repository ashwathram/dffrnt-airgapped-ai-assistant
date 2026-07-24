# DFFRNT Control Panel (installer/manager)

The single management surface for the stack — there are no shell scripts on
targets anymore (only the two packaging scripts remain in `deploy/`, and
they run on the build machine). One codebase, two faces:

- **Browser panel** (launch with no arguments): a stdlib HTTP server
  (`web/server.py`, bound to 127.0.0.1, token-gated) serves four views to
  your browser — **Install** (first-run deployment from a
  `dffrnt-*.tar.gz` bundle: pick bundle + dest, prereq gate, unpack via
  stdlib `tarfile`, `docker load`, first start), **Manage**
  (start/stop/restart, status, reingest), **Models** (switch the active
  LLM; move models on/off an air-gapped machine as tarballs — see below),
  **Logs** (follow container logs, streamed over SSE). The browser is the
  view layer: no Tk, no Qt, nothing platform-specific to render — which is
  what lets the manager ship for macOS without a Mac in the build loop.
- **CLI** (`cli.py`, any argument): the same verbs headless —
  `install`, `start`, `stop`, `restart`, `status`, `logs`, `audit`,
  `reingest`, `dev`, `panel`, `models list|pull|rm|use|export|import` —
  for SSH'd or displayless boxes (AWS targets). `panel --no-browser`
  serves the UI without opening anything, for SSH port-forwarding.

Runs unchanged on Linux, Windows, and macOS — stdlib only, end to end.

**Shipping:** `deploy/package.sh` freezes this package (PyInstaller, the
`package` dependency group) into a self-contained `dffrnt-manager` binary
(the web assets ride along as bundled data) and ships it twice: next to
the tarball in `dist/` (bootstrap install on a box that has only Docker)
and inside the bundle (managing the installed stack from the app root).
The binary is platform-specific — package on a machine matching the
target, like the container images. macOS instead ships the package as
*source* plus a **vendored relocatable CPython** fetched by
`package-macos-portable.sh` (python-build-standalone — macOS ships no
system Python), with a `dffrnt-manager` shell launcher that wraps them, so
`./dffrnt-manager` works there too — no Mac ever needed to build any of it.
The macOS install stages that same source + python + launcher into the
install directory, so it self-manages afterwards exactly like the frozen
binary does on Linux/Windows.

Host provisioning (Docker Engine / NVIDIA driver + Container Toolkit) is out
of scope — the prereq gates tell you exactly what's missing but don't install
it.

## Running it

Use the project's `uv`-managed `.venv`, not a system Python:

```bash
uv run python -m installer          # from the repo root — serves + opens the panel
uv run python -m installer panel --no-browser   # print the URL only
```

The panel binds to 127.0.0.1 with a per-session token in the URL it prints
and opens — management verbs can install and delete, so nothing is
reachable from the network or without the token. Remote use is an SSH
tunnel to the printed port.

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
sweep (panel and CLI alike) until they become the
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
whatever's shown live in the panel console. This is the same `logs/`
directory the API already uses for `audit.jsonl`. The
app logs its own startup context too — detected platform, resolved config,
and which backend it picked — so a support request can start from the log
file alone.

**Deliberately not logged**: `status()` polling and `stream_logs()`
follow output. Both are read-only "management" queries, not operations —
status is re-run after every action and on a timer, and log-follow output
is just Docker's own container logs, which Docker already persists. Logging
either to our file would add an unbounded amount of noise for information
that's already live in the panel or already durable elsewhere. See
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
plugin (plus the relocatable CPython that runs this manager), all vendored
in `dist/portable/macos/` by
`deploy/package-macos-portable.sh` — nothing installed system-wide, and
all runtime state (COLIMA_HOME/LIMA_HOME/DOCKER_CONFIG) contained under
the install's `portable/` directory. The API container reaches the native
Ollama via `host.docker.internal` (compose stdin override with
`depends_on: !override` to drop the never-started ollama container).

The portable classes subclass the container ones at explicit seams
(`_env`, `_ollama_cmd`, `_preflight`, `_compose_up`; installer:
`_backend_for`, `_post_unpack`, `_image_tars`, `_load_env`), so the
lifecycle flow, model ensure/prune/store operations, health waits, and
reingest are single-sourced — and the UI layer needed no changes at all.

**Air-gap caveat (macOS only):** colima's *first* start downloads its VM
guest image. Warm it on a networked Mac before transferring `dist/`, or
allow one-time network access at install. Everything else (models, images,
binaries) is fully offline. See `package-macos-portable.sh`'s header.

## Layout

```
installer/
  __main__.py             bare launch -> serve the panel; any argument -> CLI
  cli.py                  headless CLI over the same backends
  model_store.py          Ollama store walk, tarball export/import, models.keep
  platform_detect.py      OS/arch/GPU detection, the Pathway enum
  config.py               config.toml read/WRITE, bundle.conf, app-root resolution
  logging_setup.py        installer.log file handler + the with_logging() output-tap helper
  process.py              subprocess streaming + the BackgroundJob/LogFollower thread bridge
  backends/
    __init__.py            Backend ABC + PrereqCheck/ServiceStatus/BackendError + make_backend
    docker_backend.py       CONTAINER pathway — compose lifecycle + model ensure/prune
    portable_backend.py     PORTABLE pathway — native Metal Ollama + colima containers
  installers/
    __init__.py            Installer ABC + BundleInfo/InstallError + find_bundles/make_installer
    docker_installer.py     CONTAINER pathway — unpack, image load, first start
    portable_installer.py   PORTABLE pathway — + runtime staging, skips the ollama image
  web/
    server.py               127.0.0.1 http.server: token auth, JSON API, single-flight
                            job runner with SSE streaming (history replay), log follow
    static/index.html       the four views (Install / Manage / Models / Logs)
    static/style.css        design tokens ported from dffrnt_assistant/ui/styles
    static/app.js           busy lock, confirm modals, SSE consoles, rendering
  assets/icon.png           favicon + brand mark, from ui/img/dffrnt_favicon.jpg
```

The panel opens on Manage when an installed stack is detected, otherwise
on Install; a successful install re-points the server's context at the new
app root in place, and a page reload mid-job re-attaches to the running
job's output (full history replay over SSE).

## Design language

The stylesheet ports `dffrnt_assistant/ui/styles/theme.css`'s custom
properties directly — same navy sidebar (`#091A29`), light content area,
card/pill/`.nav-btn` vocabulary, primary/ghost/danger buttons, and status
colors (green/red/amber) as the web UI's document library. Being real CSS
this is now a faithful port (rounded cards, shadows — everything ttk
couldn't do). Fonts use the same Inter/JetBrains Mono stacks with system
fallbacks; the panel doesn't duplicate the app's woff2 files.

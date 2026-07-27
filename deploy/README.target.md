# DFFRNT AI Assistant — deployment bundle (@MODE@)

This folder contains everything needed to deploy the assistant:

- `@NAME@.tar.gz` — the application bundle
- `dffrnt-manager` — the installer + control panel (one binary; browser UI and CLI)
- `README.md` — this file

Target: **@MODE@**  ·  Models: **@MODELS@**

The app runs as a Docker container, so the target needs **only Docker** (Engine +
the Compose v2 plugin) — no Python, uv, pip, or shell scripts. `dffrnt-manager`
is self-contained: launched with no arguments it serves the control panel to
your browser (127.0.0.1 only, token-gated URL) and opens it; given any command
it runs fully headless, so it works identically over SSH on a displayless box
(`panel --no-browser` prints the URL for an SSH tunnel).

## Install

In a browser: run `./dffrnt-manager` and use the **Install** tab (it auto-detects
the tarball next to it, and you pick the destination).

Headless / SSH:

```bash
./dffrnt-manager install                    # auto-detects the tarball, installs to ./dffrnt
./dffrnt-manager install --dest /opt/dffrnt # ...or choose an install directory
```

Install checks prerequisites and reports exactly what is missing if a check
fails. It then unpacks the bundle, loads the container image(s), and starts the
Qdrant + Ollama + API stack — pulling the base images and models the first time
on an online build. An existing edited `config.toml` is kept by default
(`--overwrite-config` replaces it, archiving the old file as `config.toml.old`).

> **@MODE@ build.** An OFFLINE bundle carries every image and the Ollama model
> store, so install needs no internet. An AWS bundle ships only the app image and
> pulls the Qdrant/Ollama base images and the models from the internet at deploy
> time, which keeps it small.

## Run

A copy of `dffrnt-manager` is placed in the install directory. No arguments
serves the browser panel (Manage / Models / Logs tabs); commands run headless:

```bash
cd dffrnt                      # or your chosen install dir
./dffrnt-manager               # browser control panel (prints + opens a local URL)
./dffrnt-manager start         # bring the whole stack up
./dffrnt-manager stop          # stop all containers
./dffrnt-manager restart
./dffrnt-manager status        # service + API health (exit 1 if degraded)
./dffrnt-manager logs          # follow container logs (optionally: logs api)
./dffrnt-manager audit         # follow the app audit trail (logs/audit.jsonl)
./dffrnt-manager reingest      # force re-ingest every stored document (previews first)
```

The UI is at <http://localhost:8000>.

## Models

The active LLM can be switched without editing any file:

```bash
./dffrnt-manager models                      # list the store (sizes + roles)
./dffrnt-manager models use qwen3:8b         # switch the LLM + restart
```

Switching rewrites `llm_model` in `config.toml` and restarts; the previously
configured model is removed from the cache so disk usage doesn't grow with
every switch.

**Getting a new model onto an OFFLINE machine** (no internet to pull from): on
any networked machine with this app,
`./dffrnt-manager models export qwen3:8b /media/usb/qwen3-8b.ollama.tar`
(pulls first if absent; the drive must not be FAT32 — its 4 GiB file limit is
smaller than most models). Then on this machine:

```bash
./dffrnt-manager models import /media/usb/qwen3-8b.ollama.tar   # checksum-verified
./dffrnt-manager models use qwen3:8b
```

Both operations are also available in the panel's **Models** tab. Imported models
are protected from the disk-reclaim sweep until you switch to or delete them.

## Configuration

Everything else is `config.toml` in the install directory, then
`./dffrnt-manager restart`. It is the single source of truth for the models,
prompt, and retrieval settings, and it drives the host ports and GPU
acceleration (`gpu = true` — requires the NVIDIA driver + Container Toolkit on
the host, e.g. `nvidia-container-toolkit` from your distro or NVIDIA's repo;
the manager refuses to start GPU mode without them and says so). The API
container always serves on port 8000 internally; editing `api_port` moves only
the host-side port.

Switching `embed_model` is deliberately NOT exposed as a command: it changes
the vector dimension and requires re-uploading/re-ingesting every document.

On every start the API pre-loads the LLM and embedder into memory in the
background (they then stay resident), so the first query answers at full speed
once warmup finishes — on a fresh online install the very first warmup waits for
the model pull and can take a few minutes.

## Security

The API and UI have **no authentication**: anyone who can reach the port can
query, upload, and delete documents. Expose it only to trusted networks — on
AWS, restrict the security group for port 8000 to your VPN/office CIDR (or put
an authenticating reverse proxy in front). Never open it to 0.0.0.0/0.

## Reverse proxy and streaming

The answer and upload endpoints stream ndjson, and the app sends
`X-Accel-Buffering: no` on those responses so nginx (and most CDNs) relay tokens
as they are produced. If you front the API with a reverse proxy, its own
buffering can still clump the stream so the answer arrives in bursts instead of
token by token. For the streaming routes, turn buffering and compression off —
in nginx, scope it to just those paths so other responses keep buffering:

```nginx
location ~ ^/api/(query|upload)/stream {
    proxy_pass http://127.0.0.1:8000;
    proxy_buffering off;          # relay tokens instead of accumulating them
    gzip off;                     # the compressor re-clumps a token stream
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_read_timeout 600s;      # match llm_timeout so long generations survive
}
```

Apply it live with `nginx -t && nginx -s reload` (graceful, no dropped
connections). `proxy_buffering off` is the actual fix; `gzip off` matters only
if gzip is enabled upstream. If a CloudFront/ALB also sits in front, it can
buffer independently — confirm with `curl -N` straight at nginx (bypassing the
CDN) after reloading.

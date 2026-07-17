# DFFRNT AI Assistant — deployment bundle (@MODE@)

This folder contains everything needed to deploy the assistant:

- `@NAME@.tar.gz` — the application bundle
- `install.sh` — the installer
- `README.md` — this file

Target: **@MODE@**  ·  Models: **@MODELS@**

The app runs as a Docker container, so the target needs **only Docker** (Engine +
the Compose v2 plugin) — no Python, uv or pip.

## Install

```bash
./install.sh                 # unpacks to ./dffrnt and brings the stack up
./install.sh /opt/dffrnt     # ...or choose an install directory
```

The installer checks prerequisites and reports exactly what is missing if a check
fails. It then unpacks the bundle, loads the container image(s), and starts the
Qdrant + Ollama + API stack — pulling the base images and models the first time on
an online build.

> **@MODE@ build.** An OFFLINE bundle carries every image and the Ollama model
> store, so install needs no internet. An AWS bundle ships only the app image and
> pulls the Qdrant/Ollama base images and the models from the internet at deploy
> time, which keeps it small.

## Run

A `dffrnt_ctrl_panel.sh` is placed in the install directory. Run it with no
argument for an interactive menu, or pass a command directly — it manages the
runtime the same way the VS Code tasks do (the containers plus the API):

```bash
cd dffrnt                       # or your chosen install dir
./dffrnt_ctrl_panel.sh          # interactive menu
./dffrnt_ctrl_panel.sh start    # bring the whole stack up
./dffrnt_ctrl_panel.sh stop     # stop all containers
./dffrnt_ctrl_panel.sh restart
./dffrnt_ctrl_panel.sh status   # container + API health
./dffrnt_ctrl_panel.sh logs     # follow container logs (optionally: ./dffrnt_ctrl_panel.sh logs api)
./dffrnt_ctrl_panel.sh audit    # follow the app audit trail (logs/audit.jsonl)
./dffrnt_ctrl_panel.sh reingest # force re-ingest every stored document in the live API
```

The UI is at <http://localhost:8000>.

## Configuration

Edit `config.toml` in the install directory, then `./dffrnt_ctrl_panel.sh restart`. It is the
single source of truth for the LLM/embed models, prompt, and retrieval settings,
and it drives the host ports and GPU acceleration (`gpu = true` — requires the
NVIDIA driver + Container Toolkit on the host; `install-prerequisites.sh` sets
both up on a fresh Ubuntu box, and the control panel refuses to start GPU mode
without them). The API container always serves on port 8000 internally; editing
`api_port` moves only the host-side port.

Switching `llm_model`/`embed_model` and restarting pulls the new model (online
builds) and removes the previously configured model from the cache, so disk
usage doesn't grow with every switch. An OFFLINE bundle must have already
vendored the new model at package time (`deploy/package.sh`) — offline installs
have no internet to pull one on demand.

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

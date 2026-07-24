# DFFRNT AI Assistant — Installer Guide

This guide walks you through installing the DFFRNT Air-Gapped AI Assistant on a
target machine, from receiving the installer bundle to a running system. It is
written for a general audience — no prior experience with Docker or the command
line is assumed beyond being able to open a terminal and type commands.

---

## 1. Concepts and technologies

You do not need to master any of these to install the assistant, but knowing
what each piece does makes the process (and any error messages) much less
mysterious.

### The assistant itself

The DFFRNT AI Assistant is a private, fully offline "RAG" (Retrieval-Augmented
Generation) system. It ingests company documents (proposals, resumes, policies,
spreadsheets, …) and answers questions about them with citation-backed
responses through a web page in your browser. **No data ever leaves the
machine** — the language model, the document index, and the application all run
locally.

### Docker

[Docker](https://www.docker.com/) is software that runs applications inside
**containers** — self-contained boxes that carry everything an application
needs (its code, libraries, and settings). Because a container ships with
everything included, the assistant behaves identically on any machine, and the
target machine needs almost nothing pre-installed — **only Docker itself**. No
Python, no packages, no scripts.

Related terms you will encounter:

- **Image** — a frozen snapshot of an application, like an installation CD.
  The bundle ships images; installing "loads" them into Docker.
- **Container** — a running copy of an image. Stopping the stack stops the
  containers; the images stay behind for the next start.
- **Docker Compose** — a Docker feature that starts and connects several
  containers together as one "stack". The assistant's stack has three
  services: Qdrant, Ollama, and the API/UI.

### Ollama

[Ollama](https://ollama.com/) is a local server for large language models
(LLMs). It hosts two models for the assistant: the chat model (the `qwen3`
family) that writes the answers, and an embedding model (`bge-m3`) that turns
text into vectors for searching. Ollama runs in its own container and is not
visible to you day-to-day.

### Qdrant

[Qdrant](https://qdrant.tech/) is a **vector database**. When documents are
ingested, they are split into chunks and each chunk is stored as a vector (a
list of numbers capturing its meaning). When you ask a question, Qdrant finds
the chunks whose meaning is closest to the question, and those chunks become
the evidence the model answers from. Qdrant also runs in its own container.

### dffrnt-manager

`dffrnt-manager` is the single tool you interact with. It is one
self-contained program with two faces:

- Run it **with no arguments** and it opens a control panel in your web
  browser (Install / Manage / Models / Logs tabs). This is the recommended
  path for most users.
- Run it **with a command** (`install`, `start`, `status`, …) and it does the
  same job headlessly in the terminal — useful over SSH or on servers.

### OFFLINE vs. online (AWS) bundles

The bundle comes in two flavours, chosen when it was built:

- **OFFLINE** — carries every container image *and* the AI models inside the
  bundle. Installing needs **no internet at all**. This is the flavour for
  air-gapped machines. The bundle is large (several GB).
- **AWS / online** — ships only the application image and downloads the rest
  (Qdrant, Ollama, models) from the internet during installation. Smaller
  bundle, but the target must be online for the first install.

The README inside the bundle states which flavour you have.

---

## 2. Step-by-step installation

### What you should end up with

The installer is distributed as a single `.tar` archive. Unpacking it yields
exactly **three files, which must stay together in the same folder**:

```
dffrnt-offline.tar.gz    (or dffrnt-aws.tar.gz — the application bundle)
dffrnt-manager           (the installer + control panel, one program)
README.md                (target-side notes generated at build time)
```

### Step 0 — Check the prerequisites

The target machine needs:

1. **Docker Engine with the Compose v2 plugin.**
   - Linux: install `docker` and `docker-compose-plugin` from your
     distribution or from [docs.docker.com](https://docs.docker.com/engine/install/).
   - Windows / macOS: install **Docker Desktop** and make sure it is running
     (whale icon in the system tray / menu bar).
   - Verify with: `docker --version` and `docker compose version`.
2. **Disk space** — allow at least 25 GB free for an OFFLINE install (images,
   models, and your document index all live on disk).
3. On Linux, your user should be able to run Docker without `sudo` (see
   [Troubleshooting](#5-troubleshooting) if `docker ps` says
   "permission denied").

Don't worry about getting this perfect — the installer checks all
prerequisites first and reports exactly what is missing if a check fails,
without changing anything on the machine.

### Step 1 — Get the archive onto the machine

**Option A — download from a GitHub release (online machine):**

```bash
curl -L -o dffrnt-installer.tar \
  https://github.com/ashwathram/dffrnt-airgapped-ai-assistant/releases/download/<TAG>/dffrnt-installer.tar
```

Replace `<TAG>` with the release version you were given (e.g. `v1.0.0`). You
can also simply download it from the release page in a browser.

**Option B — USB thumb drive (air-gapped machine):**

1. On a networked machine, download the `.tar` as above and copy it to the
   drive.
2. The drive must **not** be FAT32-formatted — FAT32 cannot hold files over
   4 GB, and an OFFLINE bundle is larger than that. Use exFAT or NTFS
   (most drives sold as "64 GB or larger" are already exFAT).
3. Plug the drive into the target machine and copy the `.tar` to somewhere
   like your home folder or Desktop.

### Step 2 — Unpack the archive

In a terminal, in the folder holding the `.tar`:

```bash
mkdir dffrnt-installer
tar -xf dffrnt-installer.tar -C dffrnt-installer
cd dffrnt-installer
ls
```

`ls` should show the three files listed above. If your archive unpacked into a
nested subfolder, `cd` into it — the point is to run the next command from the
folder that directly contains `dffrnt-manager` and the `.tar.gz`.

On Windows or macOS you can instead right-click the archive and choose
"Extract" — then open a terminal in the extracted folder.

### Step 3 — Run the installer

**Browser (recommended):**

```bash
./dffrnt-manager
```

This opens the control panel in your browser (it serves only to this machine —
nothing is exposed to the network). Go to the **Install** tab: it auto-detects
the `.tar.gz` sitting next to it; you pick the destination folder and click
Install.

**Terminal (headless / SSH):**

```bash
./dffrnt-manager install                     # installs to ./dffrnt
./dffrnt-manager install --dest /opt/dffrnt  # or choose the destination
```

Either way, the installer:

1. checks the prerequisites (and stops with a clear message if one fails),
2. unpacks the application bundle into the destination folder,
3. loads the container image(s) into Docker,
4. starts the stack — Qdrant, Ollama, and the API/UI.

An OFFLINE install runs entirely from the bundle. An online (AWS) install
pulls the base images and models from the internet at this point, so the first
install can take a while depending on your connection.

### Step 4 — Verify

```bash
cd dffrnt                    # or the destination you chose
./dffrnt-manager status
```

`status` reports the health of each service. When everything is up, open
**<http://localhost:8000>** in a browser — that is the assistant.

Note: on every start the assistant pre-loads the models into memory in the
background. The very first question after a start may take a little longer
while that warmup finishes (and on a fresh *online* install, the first warmup
also waits for the model download).

### Step 5 — Day-to-day management

A copy of `dffrnt-manager` was placed in the install folder; it manages the
stack from there. Running it with no arguments opens the panel
(Manage / Models / Logs tabs); the same verbs work in the terminal:

```bash
cd dffrnt
./dffrnt-manager             # browser control panel
./dffrnt-manager start       # bring the stack up
./dffrnt-manager stop        # stop all containers
./dffrnt-manager restart
./dffrnt-manager status      # service + API health
./dffrnt-manager logs        # follow container logs (or: logs api)
./dffrnt-manager audit       # follow the app's audit trail
./dffrnt-manager reingest    # force re-ingest of every stored document
./dffrnt-manager models      # list / switch / import / export models
```

---

## 3. Accessing the control panel over SSH (AWS)

**You only need this section for a remote, headless box you administer over
SSH — in practice, an AWS instance.** On any local machine — a Linux, Windows,
or macOS desktop sitting in front of you — running `./dffrnt-manager` opens the
panel in your browser directly, and none of this applies.

Even on AWS it is **optional**: every management action is also a headless CLI
command (see [Step 5](#step-5--day-to-day-management)), so you can run the whole
deployment over a plain SSH session without ever opening the panel. Use the
tunnel below only if you prefer the graphical Install / Manage / Models / Logs
views.

### Why a tunnel is needed

For safety the panel binds to **127.0.0.1 only** (the machine's own loopback)
and puts a random per-session token in the URL it prints. Loopback-only means
it is deliberately *not* reachable across the network — so on a remote box you
reach it by forwarding your local traffic into that loopback over the SSH
connection you already have. **You do not — and should not — open port 8901 (or
8000) in the AWS security group for this.** The tunnel rides entirely inside
SSH (port 22); the panel stays invisible to the internet.

### Using a SOCKS proxy (`ssh -D`)

A dynamic SOCKS proxy is the tidiest option, because it lets your browser use
the *exact* `http://127.0.0.1:PORT/…` URL the panel prints — unchanged, token
and all. The browser hands `127.0.0.1` to the proxy, and SSH resolves it on the
*remote* loopback, which is where the panel lives.

**1. On the AWS box**, start the panel without opening a browser, on a fixed
port so it's predictable:

```bash
./dffrnt-manager panel --no-browser --port 8901
```

Copy the full URL it prints — it includes the token, e.g.
`http://127.0.0.1:8901/?token=ab12cd34…`.

**2. On your own machine**, open a SOCKS proxy over SSH and leave it running:

```bash
ssh -D 1080 -N user@your-aws-host
```

`-D 1080` opens a SOCKS proxy on local port 1080; `-N` says "just forward, don't
run a remote shell". (Add `-f` to push it into the background.)

**3. Point your browser at the proxy:**

- **Firefox:** Settings → Network Settings → *Manual proxy configuration* →
  SOCKS Host `127.0.0.1`, Port `1080`, select **SOCKS v5**, and tick **Proxy
  DNS when using SOCKS v5**.
- **Chrome / Chromium:** launch it with
  `--proxy-server="socks5://127.0.0.1:1080"`, or use a proxy-switcher
  extension so you don't reroute your everyday browsing.

**4. Open the panel.** Paste the exact URL the box printed
(`http://127.0.0.1:8901/?token=…`) into that browser. The request tunnels to
AWS, where `127.0.0.1:8901` is the panel — you now have the full control panel
as if you were sitting at the machine.

When you're done, remove the browser's proxy setting and stop the SSH session
(Ctrl-C, or `kill` it if you used `-f`).

> **Note:** the SOCKS proxy reroutes *all* of that browser's traffic through
> the AWS box while it's set. Use a separate browser profile or a
> proxy-switcher extension, and remember to turn the proxy off afterwards —
> otherwise normal browsing will stall once the tunnel closes.

### Alternative: local port forwarding (`ssh -L`)

If you'd rather not touch any browser proxy setting, forward a single local
port to the panel instead:

```bash
ssh -L 8901:127.0.0.1:8901 -N user@your-aws-host
```

Then open `http://127.0.0.1:8901/?token=…` (the same printed URL) in your normal
browser — no proxy configuration needed. The catch is that the local port must
match the panel's port, which is why we fixed it with `--port 8901` above.

---

## 4. FAQ

**Do I need to know Docker to use this?**
No. `dffrnt-manager` drives Docker for you — install, start, stop, status, and
logs are all one command or one click. Docker just needs to be installed and
running.

**How do I see what's running?**
`./dffrnt-manager status` is the friendly view. If you're curious about the
underlying containers, `docker ps` lists them (you'll see three: qdrant,
ollama, and the api), and Docker Desktop shows the same thing graphically on
Windows/macOS. You should not need to touch containers directly — always
prefer the manager, which starts and stops them in the right order.

**Does the machine need internet?**
For an **OFFLINE** bundle: no, not even during install. For an **AWS/online**
bundle: yes, once, during install (and when pulling a new model later). After
that, the assistant itself never calls out — everything runs locally.

**Where do my documents and data live?**
Inside the install folder: the vector index in `qdrant_storage/`, the AI
models in `ollama_models/`, uploaded documents and app data in `data/`, and
logs in `logs/`. Deleting the install folder deletes your data.

**How do I stop it / start it after a reboot?**
`./dffrnt-manager stop` and `./dffrnt-manager start` from the install folder.
The stack does not start automatically on boot unless you set that up
yourself.

**What is the address the panel opens, and why does it look odd?**
The control panel serves on `127.0.0.1` (this machine only) with a one-time
token in the URL — that's a safety measure so nothing on the network can reach
the management functions. The assistant itself is the friendlier
`http://localhost:8000`.

**Can other people on the network use the assistant?**
If they can reach port 8000 on this machine, yes — and note the app has **no
login**: anyone who can reach the port can query, upload, and delete
documents. Only expose it to networks you trust.

**How do I change the AI model?**
Panel → **Models** tab, or `./dffrnt-manager models use qwen3:8b`. On an
air-gapped machine, first bring the model over as a tarball:
`models export` on any networked machine with this app, then
`models import` here. Both are in the Models tab too.

**Can I change settings?**
Yes — `config.toml` in the install folder holds every setting (models, ports,
GPU on/off, retrieval tuning). Edit it, then `./dffrnt-manager restart`.

**Will reinstalling wipe my settings?**
No. An existing edited `config.toml` is kept by default; the installer only
replaces it if you explicitly pass `--overwrite-config` (the old file is then
archived as `config.toml.old`).

**Does anything get sent to the cloud?**
No. The models run locally under Ollama, the index is local Qdrant, and the
app makes no external calls. That is the point of the air-gapped design.

---

## 5. Troubleshooting

### "permission denied" when the installer (or `docker ps`) talks to Docker

On Linux, your user isn't in the `docker` group. Fix:

```bash
sudo usermod -aG docker $USER
```

then **log out and back in** (or run `newgrp docker` in the current
terminal). Verify with `docker ps` — it should list containers (or print an
empty table) without `sudo`.

### `./dffrnt-manager: Permission denied`

The executable bit was lost in transfer (common when the file passed through a
FAT32 drive or some download tools). Fix:

```bash
chmod +x dffrnt-manager
```

### `cannot execute binary file` or `Exec format error`

The bundle was built for a different OS or CPU architecture than this machine
(e.g. an x86_64 build on an ARM machine). Bundles are platform-specific — ask
for a build matching the target and check with `uname -m`.

### macOS blocks the program ("cannot be opened because the developer cannot be verified")

macOS quarantines files that arrived from the internet. Clear it with:

```bash
xattr -d com.apple.quarantine dffrnt-manager
```

or right-click → Open the first time.

### "No bundle found" / installer can't find the tarball

The three files must sit **together in the same folder**, and you must run
`./dffrnt-manager` from that folder. Check with `ls` that you see the
`dffrnt-*.tar.gz` next to `dffrnt-manager` — if extraction created a nested
subfolder, `cd` into it. You can also name the bundle explicitly:
`./dffrnt-manager install path/to/dffrnt-offline.tar.gz`.

### A prerequisite check fails

The message names exactly what's missing — most commonly Docker isn't
installed, isn't running (start Docker Desktop, or `sudo systemctl start
docker` on Linux), or the Compose v2 plugin is absent (`docker compose
version` should print a version). Install/start the missing piece and re-run;
the check changed nothing, so it's safe to retry.

### Port 8000 is already in use

Another program on the machine owns port 8000. Edit `api_port` in
`config.toml` in the install folder (e.g. `api_port = 8080`), then
`./dffrnt-manager restart`, and use `http://localhost:8080`.

### `status` says a service is unhealthy / the UI won't load

Give it a minute after `start` — the models take time to load. Then:

```bash
./dffrnt-manager status      # which service is degraded?
./dffrnt-manager logs api    # read that service's log (also: logs ollama, logs qdrant)
./dffrnt-manager restart     # often clears one-off startup races
```

### GPU mode refuses to start

`gpu = true` in `config.toml` requires the NVIDIA driver **and** the NVIDIA
Container Toolkit on the host; the manager checks and refuses with a message
if either is missing. Install them (e.g. `nvidia-container-toolkit` from your
distro or NVIDIA's repository), or set `gpu = false` to run on CPU.

### The USB drive won't take the bundle / a model export

The drive is FAT32, whose 4 GB per-file limit is smaller than the bundle and
most models. Reformat the drive as exFAT (both Windows and macOS/Linux can
read and write it) and copy again.

### Disk fills up over time

Model switching is designed not to accumulate: switching removes the
previously configured model from the cache. If space runs low anyway, check
`./dffrnt-manager models` for unused models (`models rm NAME`) and
`docker system df` for Docker's own usage.

### Something else

`./dffrnt-manager logs` (all services) and `logs/installer.log` in the install
folder record what happened — include the relevant lines when asking for help.

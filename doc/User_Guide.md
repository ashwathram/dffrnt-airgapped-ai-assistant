# DFFRNT AI Assistant — User Guide

This guide covers everyday use of the DFFRNT Air-Gapped AI Assistant: managing
the stack with **dffrnt-manager**, working in the **assistant application**
itself (chat, document library, tags), performing routine tasks like swapping
models, and — in the annex — a full reference for every `config.toml`
parameter.

For getting the software onto a machine in the first place, see the companion
**Installer Guide**.

---

## 1. The dffrnt-manager application

`dffrnt-manager` is the single control surface for the whole stack. It lives
in the install folder (e.g. `dffrnt/`) and has two faces: a **browser control
panel** and an identical **command-line interface**. Everything the panel can
do, the CLI can do, and vice versa.

### 1.1 Launching

**Browser panel** — from the install folder:

```bash
cd dffrnt
./dffrnt-manager
```

This starts a small local web server and opens the panel in your default
browser. The URL looks odd on purpose: it serves on `127.0.0.1` (this machine
only) and carries a random per-session token, so nothing on the network — and
no other user on the machine — can reach the management functions.

**Remote / headless machines** — the panel can't open a browser over SSH, so
print the URL instead and tunnel to it:

```bash
./dffrnt-manager panel --no-browser     # prints the URL (note the port + token)
# on your own machine:
ssh -L 8901:127.0.0.1:8901 user@target  # then open the printed URL locally
```

**CLI** — any argument makes it run headless:

```bash
./dffrnt-manager status
```

### 1.2 The panel views

| View | What it does |
|------|--------------|
| **Install** | First-run deployment: pick the `dffrnt-*.tar.gz` bundle (auto-detected when next to the manager) and a destination, pass the prerequisite check, unpack, load images, first start. After installation you'll normally never need this view again. |
| **Manage** | Start / stop / restart the stack, live service + API health, and force a re-ingest of every stored document. |
| **Models** | See the model store (names, sizes, roles), switch the active LLM, and move models on/off an air-gapped machine as tarballs (import/export). |
| **Logs** | Follow the containers' logs live (all services or one at a time) — the first place to look when something misbehaves. |

Only one operation runs at a time — if a button reports "busy", another job
(perhaps started from a second browser tab) is still in progress. Job output
survives a page reload; you can close the tab and come back mid-install.

### 1.3 Command reference

All commands run from the install folder.

| Command | What it does |
|---------|--------------|
| `./dffrnt-manager` | Serve + open the browser panel |
| `./dffrnt-manager panel --no-browser` | Serve the panel, print the URL only (SSH tunnels); `--port N` fixes the port |
| `./dffrnt-manager install [BUNDLE] [--dest DIR] [--overwrite-config]` | Deploy a bundle (auto-detects one next to the binary) |
| `./dffrnt-manager start` | Bring the whole stack up (Qdrant + Ollama + API) |
| `./dffrnt-manager stop` | Stop all services |
| `./dffrnt-manager restart` | Stop, then start — required after editing `config.toml` |
| `./dffrnt-manager status` | Per-service + API health; exits non-zero if degraded (script-friendly) |
| `./dffrnt-manager logs [all\|qdrant\|ollama\|api]` | Follow service logs (Ctrl-C to stop) |
| `./dffrnt-manager audit` | Follow the application audit trail (`logs/audit.jsonl`) |
| `./dffrnt-manager reingest [--dry-run] [--yes]` | Force re-ingest of every stored document (previews first) |
| `./dffrnt-manager models` | List the model store with sizes and roles |
| `./dffrnt-manager models use NAME` | Switch the active LLM and restart |
| `./dffrnt-manager models pull [NAME...]` | Pull model(s) from the internet (online machines) |
| `./dffrnt-manager models rm NAME` | Delete a model from the store |
| `./dffrnt-manager models export NAME DEST.tar` | Pack a model into a tarball (for USB transfer) |
| `./dffrnt-manager models import TARBALL` | Load a model tarball into the store (checksum-verified) |

### 1.4 Manager FAQ

**Do I have to keep the panel open?**
No. The panel is only a remote control — closing the tab (or the whole
manager) leaves the assistant running. The stack keeps serving until you
`stop` it.

**The panel URL stopped working after I restarted the manager.**
That's expected: the token in the URL is minted per session. Run
`./dffrnt-manager` again and use the newly printed/opened URL.

**Can two people manage at once?**
The panel accepts one mutating operation at a time; a second request gets a
"busy" response until the first finishes. Status and log views are read-only
and always available.

**Where does the manager itself log?**
`logs/installer.log` in the install folder records every manager operation;
`./dffrnt-manager logs` follows the *services'* logs instead.

**Does the CLI have anything the panel doesn't?**
`audit` (following the app audit trail) and `dev` (a development mode for
source checkouts) are CLI-only. Everything an operator needs day-to-day is in
both.

### 1.5 Manager troubleshooting

- **"busy" that never clears** — a long job (model pull, re-ingest) is still
  running; watch it in Logs. If the manager truly died mid-job, restart the
  panel process and check `./dffrnt-manager status`.
- **Panel opens but every action fails** — usually Docker stopped underneath
  it. Check `docker ps`; start Docker (Desktop or `systemctl start docker`)
  and retry.
- **`status` exits degraded right after `start`** — services take a moment to
  pass health checks, and the models take longer to warm. Wait a minute and
  re-run.
- For permissions problems, missing bundles, and port conflicts, see the
  Installer Guide's troubleshooting section — those issues are identical
  post-install.

---

## 2. The DFFRNT Assistant application

Open **http://localhost:8000** in a browser (any modern browser on the
machine, or on the network if the port is exposed — remember the app has no
login). The window has two areas:

- a **sidebar** on the left — brand, *New chat*, *Document Library*, a search
  box, and your recent conversations (collapsible via the toggle at the top);
- the **main area** — either the chat panel or the Document Library.

The assistant answers **only from the documents in its library**. If the
documents don't contain the answer, it says so rather than guessing — that is
deliberate. So the workflow is: upload documents → organise them with tags →
ask questions.

### 2.1 The chat interface

Type a question into the composer ("Ask anything about your documents…") and
press **Enter** (or the send button). The answer streams in token by token.

**Thinking.** The models are reasoning models: they "think" before answering.
The **Thinking on/off** pill above the composer controls whether that
reasoning is shown as a live block above the answer or folded away behind a
"Thinking…" label. It's a display choice only — the model reasons either way —
and it persists across sessions.

**Citations and sources.** Every claim in an answer carries an inline
bracketed citation like `[1]` or `[2][3]`. The numbers map to the source list
shown with the answer; clicking a citation highlights the matching source.
This is your audit trail — the disclaimer under the composer means what it
says: *verify important information from source documents*.

**Message actions.** Hovering a message reveals its actions:

- **Copy** — copy the message text to the clipboard.
- **Retry** — regenerate the assistant's answer to the same question (useful
  after changing scope or uploading more documents).
- **Download** — save an answer as **Plain text (.txt)**, **Markdown (.md)**,
  or **PDF (.pdf)**.
- **Stop** — while an answer is streaming, stop generation.

**Refusals.** "The available documents do not contain enough information to
answer this." is the assistant declining to guess. If you believe the answer
*is* in the library, rephrase with the document's own vocabulary, widen or
clear the retrieval scope (below), or check the document actually ingested
(Library → does it appear, with the right tags?).

### 2.2 Conversations

Every chat is saved automatically and appears under **RECENT** in the
sidebar:

- click a conversation to reopen it — the full history, sources included;
- **Search chats…** filters the list as you type;
- the trash button next to RECENT clears all conversations (confirmation
  asked);
- **New chat** starts a fresh conversation — the assistant carries recent
  turns of the *current* conversation as context, so start a new chat when
  you change topic to keep answers sharp.

### 2.3 Retrieval scope (searching within tags)

Above the messages sits the **scope bar**. Expand it to see the tag taxonomy
grouped by type, and click tags to restrict retrieval: the assistant will
then search **only documents carrying at least one selected tag** (OR
semantics). The bar shows how many documents are currently in scope.

Typical uses: scope to `Resumes` before asking "which candidates know
Figma?", or to a project tag before asking for a timeline summary. Clear the
scope to search the whole library again. Scope applies per conversation and
is sent with every question while active.

### 2.4 The Document Library

Sidebar → **Document Library**. This is the assistant's knowledge base — a
table of every ingested document with its type, size, tags, description, and
upload info, plus a storage summary.

- **Search documents…** — free-text filter on name and description.
- **Tag filter** — click tag chips to filter the table (multiple tags narrow
  it down: a document must carry all of them).
- **Inline editing** — each row lets you edit the document's tags and its
  description in place.
- **Delete** — the row menu (⋯) removes a document from the knowledge base
  (with confirmation). Its chunks leave the vector store; answers will no
  longer draw on it.

### 2.5 Uploading documents

Library → **Upload** opens the upload modal. Add individual files or an
entire **folder** (folder uploads group under the folder's name and can share
one set of tags and a description, applied to every file inside).

- **Supported formats:** PDF, DOCX, PPTX, XLSX, CSV, TXT, and Markdown.
- **Size limit:** 50 MB per file. Oversized or unsupported files are flagged
  in the queue and skipped; remove them with the ×.
- **Tags at upload:** assign tags per file (or per folder) before uploading —
  cheaper than retagging later.
- **Duplicates:** if the server already holds a file with the same name, the
  queue flags it and you resolve it inline: **Replace** the stored copy,
  **Keep both**, or **Remove** it from the queue.

Upload streams progress per file; each document is chunked, embedded, and
searchable as soon as its ingestion finishes.

### 2.6 The tagging system

Tags are the library's organising principle, and they do double duty: they
group and filter documents in the library, **and** they scope retrieval in
chat (§2.3).

The taxonomy has two levels, managed in Library → **Manage Tags**:

- **Tag types** — categories such as *Document kind*, *Project*, or
  *Department*, each with a colour. A tag's colour comes from its type, so
  chips are visually scannable everywhere (library rows, scope bar, upload
  queue).
- **Tags** — the values inside a type (e.g. `Resume`, `Proposal`, `Policy`
  under *Document kind*).

In the Tag Manager you can create, rename, recolour, and delete types, and
add or delete tags within them. Deleting is confirmed first; a tag removed
from the taxonomy disappears from scope selection, and documents still
carrying an unknown tag show it in neutral grey.

> **Tip:** design the taxonomy before bulk-uploading. A small, consistent set
> of types (kind / project / team) beats dozens of ad-hoc tags — scoped
> questions like "summarise the *Aurora* correspondence" only work if the
> documents were tagged consistently.

---

## 3. Routine tasks and troubleshooting

### 3.1 Swapping the active model

The stack ships several `qwen3` sizes trading speed for capability. To
switch:

- **Panel:** Models view → pick the model → *Use*.
- **CLI:** `./dffrnt-manager models use qwen3:8b`

Switching rewrites `llm_model` in `config.toml` and restarts the stack. To
keep disk usage flat, the previously configured model is removed from the
cache — except imported models, which are protected until you switch to or
delete them.

**On an air-gapped machine** the model must first be brought over as a
tarball:

1. On any networked machine with this app:
   `./dffrnt-manager models export qwen3:8b /media/usb/qwen3-8b.ollama.tar`
   (pulls first if absent; the USB drive must not be FAT32 — its 4 GB file
   limit is smaller than most models).
2. On the air-gapped machine:
   `./dffrnt-manager models import /media/usb/qwen3-8b.ollama.tar` (the
   import is checksum-verified), then
   `./dffrnt-manager models use qwen3:8b`.

Both steps are also available in the panel's Models view.

> **Note:** the *embedding* model is deliberately not swappable by command.
> Changing it changes the vector dimension, which invalidates the entire
> index and requires re-uploading or re-ingesting every document. If you must
> change it, edit `embed_model` **and** `vector_size` in `config.toml`,
> restart, and run `./dffrnt-manager reingest`.

### 3.2 Changing configuration

Edit `config.toml` in the install folder (see the Annex for every
parameter), then:

```bash
./dffrnt-manager restart
```

The config file survives reinstalls (only `install --overwrite-config`
replaces it, archiving the old file as `config.toml.old`).

### 3.3 Re-ingesting the library

After changing chunking settings, or if a document seems poorly indexed:

```bash
./dffrnt-manager reingest --dry-run   # preview what would be processed
./dffrnt-manager reingest             # asks for confirmation, then runs
```

Re-ingestion re-chunks and re-embeds every stored document from the original
uploaded files. It can take a while for large libraries (each chunk is
embedded by the local model).

### 3.4 Backing up

Everything lives in the install folder — stop the stack, copy the folder,
start again:

```bash
./dffrnt-manager stop
cp -r dffrnt /backup/dffrnt-$(date +%F)
./dffrnt-manager start
```

The critical subfolders are `data/` (original uploaded documents),
`qdrant_storage/` (the vector index, tags, and saved conversations), and
`config.toml`. `ollama_models/` is bulky and reproducible (re-pull or
re-import), so you may back it up less often.

### 3.5 The audit trail

`./dffrnt-manager audit` follows `logs/audit.jsonl`, the application's
append-only record of queries, uploads, and deletions — useful for reviewing
how the knowledge base is being used on a shared machine.

### 3.6 Troubleshooting

**The first answer after a start is slow.**
On every start the models are pre-loaded into memory in the background; the
first question may land before warmup finishes. Subsequent answers run at
full speed. (On a fresh online install the very first warmup also waits for
the model download.)

**Answers are slow in general.**
Model size vs. hardware. On CPU-only machines use a smaller model
(`models use qwen3:4b`). On NVIDIA machines make sure `gpu = true` is set
and the NVIDIA Container Toolkit is installed — the manager refuses GPU mode
and says so when it isn't. On Apple Silicon the GPU (Metal) is used
automatically.

**The assistant refuses although the answer is in a document.**
See §2.1 — check scope, rephrase with the document's vocabulary, confirm the
document ingested. If retrieval consistently misses, `top_k` and
`score_margin` in the annex are the tuning knobs (re-run the evaluation suite
before trusting changes).

**Answers cite the wrong or outdated documents.**
Delete superseded documents from the library, or keep both but tag them so
scope can separate them. The system prompt prefers the latest agreed state
when documents contradict each other, but it can only work with what's
ingested.

**An upload stays "processing" or fails.**
Check `./dffrnt-manager logs api`. Common causes: a corrupt or password-
protected file, or a file over 50 MB. Fix the file and re-upload; a failed
file can simply be uploaded again.

**A service is unhealthy / the UI won't load.**
`./dffrnt-manager status` to identify the service, `logs <service>` to read
its output, `restart` to recover. See the Installer Guide for the full
troubleshooting checklist (Docker down, port conflicts, permissions).

**Streaming looks "chunky" behind a reverse proxy.**
The API streams answers token by token and marks the responses no-buffering;
an intermediate nginx/CDN can still buffer them into bursts. Disable
proxy buffering for the `/api/*/stream` routes (details in the deployment
README).

---

## Annex A — `config.toml` reference

`config.toml` in the install folder is the single source of truth for every
tunable. Values can also be set as `UPPER_SNAKE_CASE` environment variables;
precedence is **environment > config.toml > built-in default**. After any
change: `./dffrnt-manager restart`.

> **Warning:** parameters marked ⚠ invalidate the existing vector index —
> changing them requires re-uploading or re-ingesting every document.

### Deployment

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `gpu` | `false` | Enable NVIDIA GPU acceleration for Ollama (Linux/Windows container pathway). Requires the NVIDIA driver **and** Container Toolkit on the host; the manager refuses to start GPU mode without them. **Ignored on macOS**, where native Ollama uses Metal automatically. |

### Ollama — models and generation

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `ollama_url` | `http://localhost:11434` | Host-side URL of the Ollama server. Only the **port** is honoured across deployment pathways — keep the host `localhost`; the manager injects the right in-container address itself. |
| `llm_model` | `qwen3:14b` | The chat LLM. Ships in three sizes: `qwen3:4b` (~2.6 GB, CPU-viable), `qwen3:14b` (~9.3 GB, fits a 16 GB GPU alongside the embedder), `qwen3:30b-a3b` (~19 GB, needs a 24 GB GPU). Normally changed via `models use`, not by hand. |
| `embed_model` ⚠ | `bge-m3` | The embedding model that turns text into vectors. Changing it changes the vector dimension — deliberately not switchable by command. |
| `vector_size` ⚠ | `1024` | Dimension of the embedding vectors. **Must match the embed model's output dimension** (1024 for bge-m3). |
| `llm_temperature` | `0.1` | Sampling temperature. Low = factual and repeatable, which suits a grounded assistant; raise only if answers feel too rigid. |
| `llm_timeout` | `600` | Seconds before a generation request is abandoned. Local generation can legitimately be slow on big prompts. |
| `llm_num_ctx` | `16384` | Context window in tokens. Ollama's own default (4096) silently truncates RAG prompts once retrieved documents + history grow; 16384 covers worst-case aggregate retrieval plus `llm_num_predict`. Larger costs GPU memory (~1.4 GB KV cache at 16k for qwen3:14b). |
| `llm_top_p` | `0.95` | Nucleus sampling cut-off (qwen3's recommended value). |
| `llm_top_k` | `20` | Sampling candidate cut-off (qwen3's recommended value). |
| `llm_repeat_penalty` | `1.1` | Penalises repetition. At `1.0` the reasoning model can loop the same reasoning block forever on ambiguous questions; `1.1` (qwen3's thinking-mode recommendation) lets it converge. |
| `llm_num_predict` | `5000` | Hard cap on generated tokens (thinking + answer) — the runaway-generation safety net. Too low guillotines the answer mid-thought; keep well under `llm_num_ctx` minus the prompt. `-1` = unlimited (not recommended). |
| `embed_query_prefix` ⚠ | `""` | Task prefix prepended to *queries* before embedding (some models want `"search_query: "`). bge-m3 uses none — leave blank. |
| `embed_document_prefix` ⚠ | `""` | Task prefix prepended to *documents* before embedding. bge-m3 uses none — leave blank. |
| `embed_on_cpu` | `false` | Pin the embedder to CPU. Set `true` when the GPU can't hold the LLM and embedder at once — keeps the LLM resident instead of thrashing (evict-to-embed, reload-to-generate). Ingestion gets slower; chat stays warm. |

### Qdrant — vector store and retrieval

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `qdrant_url` | `http://localhost:6333` | URL of the Qdrant server. |
| `collection_name` | `dffrnt_documents` | Collection holding the document chunks. |
| `summary_collection_name` | `dffrnt_document_summaries` | Collection holding per-document summaries (used for routing aggregate queries). |
| `tags_collection_name` | `dffrnt_tags` | Collection persisting the tag taxonomy. |
| `conversations_collection_name` | `dffrnt_conversations` | Collection persisting saved conversations. |
| `distance` | `cosine` | Vector similarity metric: `cosine` \| `dot` \| `euclid`. Leave at `cosine` for bge-m3. |
| `top_k` | `8` | Retrieved-chunk candidates fetched per query. Higher = wider evidence but longer prompts (mind `llm_num_ctx`). |
| `score_margin` | `0.20` | Relative relevance cut: drop hits scoring more than this below the best hit, so weak chunks never reach the prompt. `0` disables. Corpus-dependent — re-run the evaluation suite (`pytest -m eval`) before changing. |
| `aggregate_group_limit` | `24` | For aggregate ("all candidates", tag-scoped) queries: additionally fetch the best chunk(s) from each of up to this many documents, merged into the candidate pool so roll-ups cover every relevant document. `0` disables. |
| `aggregate_group_size` | `1` | Chunks kept per document in that grouped search. |

### Chunking (⚠ all four — re-ingest after changing)

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `chunk_strategy` | `recursive` | How documents are split: `fixed` \| `sentence` \| `paragraph` \| `recursive`. Recursive respects structure (paragraphs, then sentences) while targeting the size below. |
| `chunk_size` | `512` | Target chunk size in characters. Small chunks favour precise retrieval — the priority for this application. |
| `chunk_overlap` | `64` | Characters shared between consecutive chunks, so facts on a boundary aren't split away from their context. |
| `chunk_floor` | `128` | Chunks smaller than this are merged forward, so headings and single-line fragments are never stored as useless standalone chunks. `0` disables. |

### Retrieval / prompting

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `history_turns` | `6` | How many recent conversation turns accompany each question as context. More = better follow-ups, longer prompts. |
| `system_prompt` | `""` | The assistant's standing instructions (audience, tone, citation rules, refusal rule). Blank uses the built-in default; the shipped `config.toml` carries DFFRNT's tuned prompt. Edit with care — the citation and refusal behaviour lives here. |

### API / paths

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `api_host` | `0.0.0.0` | Interface the API binds to. `0.0.0.0` = every interface (needed inside the container). |
| `api_port` | `8000` | Host-side port for the API + UI. The container always serves 8000 internally; this moves only the published port. |
| `data_dir` | `data` | Where original uploaded files are stored (relative to the install folder). |
| `audit_log_path` | `logs/audit.jsonl` | Location of the append-only audit trail. |

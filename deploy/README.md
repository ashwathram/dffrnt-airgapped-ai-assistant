# Offline deployment

Build a bundle on a networked machine, copy it to the air-gapped target, install.

## 1. Build (networked machine, matching the target OS/arch)

```bash
ollama pull qwen3:4b && ollama pull bge-m3   # vendor the models (must match config.toml)
deploy/build_offline.sh
# -> dist/offline-bundle.tar.gz
```

Pull whichever `llm_model` your `config.toml` names: `qwen3:4b` is the lightweight
default; `qwen3:30b-a3b` is the high-capacity MoE option. The embedding model is
`bge-m3` (1024-dim). `build_offline.sh` vendors whatever is in your local Ollama
model store, so make sure the model named in the bundle's `config.toml` is pulled.

The bundle contains: Python wheels (`wheelhouse/`), the app wheel, the Qdrant +
Ollama images (`images/`), the Ollama model store (`ollama_models/`), a
`docker-compose.yml`, and a starter `config.toml`.

## 2. Transfer

Copy `dist/offline-bundle.tar.gz` to the target by whatever approved means
(USB, one-way transfer, etc.) and unpack:

```bash
tar -xzf offline-bundle.tar.gz && cd offline-bundle
```

## 3. Install & run (air-gapped target)

```bash
./install_offline.sh
./start.sh                                  # starts Qdrant + Ollama (GPU if enabled)
DFFRNT_CONFIG=./config.toml ./.venv/bin/dffrnt-api
```

### GPU acceleration

GPU is driven entirely by `config.toml` — there is no separate GPU compose file.
Set `environment = "local-cuda"` (or `gpu = true`) and `start.sh` injects the
NVIDIA device reservation automatically. This requires the NVIDIA Container
Toolkit on the host; on non-GPU hosts leave the default and it runs on CPU.

## Python 3.14 note

This project targets Python 3.14. Prebuilt `cp314` wheels must exist for the
target architecture for every dependency. Because the heavy ML stack
(LangChain, torch, sentence-transformers) has been removed, the remaining
dependencies are small and broadly available — but `build_offline.sh` still
fails fast on the networked machine if any wheel is missing, so you find out
before shipping. If a wheel is genuinely unavailable, either build it from
source on a matching machine and drop it into `wheelhouse/`, or lower the
`requires-python` pin in `pyproject.toml`.

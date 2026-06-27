# DFFRNT AI Assistant — API + web UI in one image, built with uv.
#
# Multi-stage: the builder resolves the locked dependency set and the managed
# Python 3.14 interpreter with uv, producing a self-contained .venv. The runtime
# stage copies only the interpreter + venv, so neither uv nor pip ships in the
# final image. Build context is the repo root (see deploy/docker-compose.yml).
#
#   docker build -t dffrnt-assistant:latest -f deploy/Dockerfile .

# ---- builder: resolve dependencies + build the venv with uv ----------------
FROM ghcr.io/astral-sh/uv:bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_INSTALL_DIR=/python \
    UV_PYTHON_PREFERENCE=only-managed

WORKDIR /app

# Let uv fetch the 3.14 interpreter, so we don't depend on a python:3.14 base
# image existing for the target architecture.
RUN uv python install 3.14

# Dependencies first: this layer is cached until the lockfile changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# Then the application itself, installed non-editably into the venv.
COPY dffrnt_assistant ./dffrnt_assistant
RUN uv sync --frozen --no-dev --no-editable

# ---- runtime: interpreter + venv only, no uv/pip ---------------------------
FROM debian:bookworm-slim

# The managed venv symlinks into the interpreter dir, so both must come across.
COPY --from=builder /python /python
COPY --from=builder /app /app

ENV PATH="/app/.venv/bin:$PATH"
WORKDIR /app
EXPOSE 8000

# Container hostnames for the sibling services; config.toml (mounted) supplies
# the rest. Env wins over config.toml, so localhost defaults there are overridden.
ENV QDRANT_URL=http://qdrant:6333 \
    OLLAMA_URL=http://ollama:11434

CMD ["dffrnt-api"]

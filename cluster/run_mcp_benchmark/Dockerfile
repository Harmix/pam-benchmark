# MCP-memory-on-harness Benchmark (run_mcp_benchmark.py) — image for GCP Cloud
# Run Jobs. Unlike the run_benchmark image, this one also bundles the Claude
# Code CLI (Node) so the harness can drive `claude` headlessly, plus the
# google-cloud libs so `gs://` / `sm://` credentials resolve on Cloud Run.
#
# Build (from project root):
#   docker build -f cluster/run_mcp_benchmark/Dockerfile -t memory-mcp-benchmark:dev .
#
# Run locally:
#   docker run --rm --env-file secrets.env -v "$(pwd)/outputs:/app/outputs" \
#     memory-mcp-benchmark:dev \
#       --dataset locomo --harness claude-code --baseline memory_md_mcp \
#       --harness-model claude-sonnet-4-6 --exp-name smoke --max-questions 5
# (No need to repeat scripts/run_mcp_benchmark.py — it's part of the ENTRYPOINT.)

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:${PATH}" \
    PYTHONPATH=/app/src

# OS deps + Node.js 20 + the Claude Code CLI. Node stays in the final image
# because the npm-installed `claude` is a Node program.
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential ca-certificates curl gnupg \
 && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && npm install -g @anthropic-ai/claude-code \
 && rm -rf /var/lib/apt/lists/*

# uv as the package manager.
RUN pip install --no-cache-dir uv

WORKDIR /app

# Layer 1: dependencies only — maximizes Docker layer cache.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Extra libs (image-only, not in pyproject so the run_benchmark image stays
# lean): let `gs://` / `sm://` GOOGLE_APPLICATION_CREDENTIALS resolve via the
# GCP SDKs using Cloud Run's ambient service-account credentials.
RUN uv pip install --python /opt/venv/bin/python \
    google-cloud-secret-manager google-cloud-storage

# Layer 2: source + data. `src/datasets/locomo/data/locomo10.json` is allow-listed
# in `.dockerignore`, so `COPY src/ ./src/` brings it in.
COPY src/ ./src/
COPY scripts/ ./scripts/
RUN mkdir -p /app/outputs

# Fail the build early if the LoCoMo data didn't land.
RUN test -f /app/src/datasets/locomo/data/locomo10.json \
    || (echo "ERROR: locomo10.json missing from build context. Check .dockerignore." >&2 && exit 1)

# Fail the build early if the Harmix bench cases didn't land. Only the JSON is
# baked in (allow-listed in .dockerignore); per-persona memory snapshots are
# read from GCS at run time, not bundled.
RUN test -f /app/src/datasets/harmix/data/harmix_bench_cases.json \
    || (echo "ERROR: harmix_bench_cases.json missing from build context. Check .dockerignore." >&2 && exit 1)

# Fail the build early if the Claude Code CLI isn't on PATH.
RUN command -v claude >/dev/null \
    || (echo "ERROR: claude CLI not installed in image." >&2 && exit 1)

# Script is part of the ENTRYPOINT so Cloud Run Jobs `--args` go straight to
# `scripts/run_mcp_benchmark.py`.
ENTRYPOINT ["python", "scripts/run_mcp_benchmark.py"]
CMD ["--help"]

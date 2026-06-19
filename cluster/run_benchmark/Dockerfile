# PAM Benchmark (run_benchmark.py) — single image, runs locally and on GCP
# Cloud Run Jobs.
#
# Build (from project root):
#   docker build -f cluster/run_benchmark/Dockerfile -t memory-benchmark:dev .
#
# Run locally:
#   docker run --rm --env-file secrets.env -v "$(pwd)/outputs:/app/outputs" \
#     memory-benchmark:dev \
#       --dataset locomo --baseline gpt-4-turbo --exp-name smoke --max-questions 5
# (No need to repeat scripts/run_benchmark.py — it's part of the ENTRYPOINT.)

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:${PATH}" \
    PYTHONPATH=/app/src

# OS deps (build-essential needed for some wheels that lack prebuilt binaries).
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# uv as the package manager.
RUN pip install --no-cache-dir uv

WORKDIR /app

# Layer 1: dependencies only — maximizes Docker layer cache.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Layer 2: source + data. `src/datasets/locomo/data/locomo10.json` is allow-listed
# in `.dockerignore`, so `COPY src/ ./src/` brings it in. MEMTRACK and any other
# dataset data dirs remain excluded by default — re-add a negation in
# `.dockerignore` to include them.
COPY src/ ./src/
COPY scripts/ ./scripts/
RUN mkdir -p /app/outputs

# Fail the build early if the LoCoMo data didn't land — Cloud Run has no FS
# to recover from a missing data file at runtime.
RUN test -f /app/src/datasets/locomo/data/locomo10.json \
    || (echo "ERROR: locomo10.json missing from build context. Check .dockerignore." >&2 && exit 1)

# Script is part of the ENTRYPOINT so Cloud Run Jobs `--args` go straight to
# `scripts/run_benchmark.py` — never to the `python` interpreter itself.
# To run a different script, override the ENTRYPOINT, e.g.:
#   gcloud run jobs deploy ... --command python --args scripts/generate_report.py,--exp-name,X
ENTRYPOINT ["python", "scripts/run_benchmark.py"]
CMD ["--help"]

# PAM Benchmark — single image, runs locally and on GCP Cloud Run Jobs.
#
# Build (from project root):
#   docker build -f cluster/Dockerfile -t pam-benchmark:dev .
#
# Run locally:
#   docker run --rm --env-file secrets.env -v "$(pwd)/outputs:/app/outputs" \
#     pam-benchmark:dev scripts/run_benchmark.py \
#       --dataset locomo --baseline gpt-4-turbo --exp-name smoke --max-questions 5

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

# Layer 2: source.
COPY src/ ./src/
COPY scripts/ ./scripts/

# Pre-create the LoCoMo data dir so a bind-mount at runtime works cleanly.
RUN mkdir -p /app/src/datasets/locomo/data /app/outputs

# The data file is mounted (or COPYed) at runtime. To bake it into the image,
# uncomment the next line — useful for Cloud Run where there's no FS to mount:
# COPY src/datasets/locomo/data/locomo10.json /app/src/datasets/locomo/data/

# `python` so Cloud Run `--args` can pass `scripts/run_benchmark.py --dataset ...`.
ENTRYPOINT ["python"]
CMD ["scripts/run_benchmark.py", "--help"]

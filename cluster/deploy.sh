#!/usr/bin/env bash
# Build the image, push to Artifact Registry, and deploy/update the Cloud Run Job.
#
# Env vars (export or pass on the command line):
#   GCP_PROJECT          GCP project id
#   GCP_REGION           e.g. europe-west1
#   AR_REPO              Artifact Registry repo name (e.g. pam-benchmark)
#   JOB_NAME             Cloud Run Job name (default: pam-benchmark)
#   IMAGE_TAG            Image tag (default: git short SHA, falling back to 'dev')
#   SECRETS              Comma-separated NAME=secret:version pairs to inject
#                        (e.g. "OPENAI_API_KEY=openai-key:latest,CONNECTION_STRING=mongo-uri:latest,DB_NAME=mongo-db:latest")
#   TASK_TIMEOUT         Per-task timeout in seconds (default: 86400 = 24h)
#   MAX_RETRIES          (default: 0)
#
# Usage:
#   ./cluster/deploy.sh

set -euo pipefail

: "${GCP_PROJECT:?must set GCP_PROJECT}"
: "${GCP_REGION:?must set GCP_REGION (e.g. europe-west1)}"
: "${AR_REPO:?must set AR_REPO (Artifact Registry repo name)}"
: "${SECRETS:?must set SECRETS (NAME=secret:version,...)}"

JOB_NAME="${JOB_NAME:-pam-benchmark}"
IMAGE_TAG="${IMAGE_TAG:-$(git rev-parse --short HEAD 2>/dev/null || echo dev)}"
TASK_TIMEOUT="${TASK_TIMEOUT:-86400}"
MAX_RETRIES="${MAX_RETRIES:-0}"

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

IMAGE="${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT}/${AR_REPO}/${JOB_NAME}:${IMAGE_TAG}"

echo "==> Building image: $IMAGE"
docker build -f cluster/Dockerfile -t "$IMAGE" .

echo "==> Authenticating Docker to Artifact Registry"
gcloud auth configure-docker "${GCP_REGION}-docker.pkg.dev" --quiet

echo "==> Pushing image"
docker push "$IMAGE"

DIGEST="$(docker inspect --format='{{index .RepoDigests 0}}' "$IMAGE" || true)"
echo "==> Image digest: $DIGEST"

DEPLOY_CMD="create"
if gcloud run jobs describe "$JOB_NAME" --region "$GCP_REGION" --project "$GCP_PROJECT" >/dev/null 2>&1; then
    DEPLOY_CMD="update"
fi

echo "==> ${DEPLOY_CMD} Cloud Run Job: $JOB_NAME"
gcloud run jobs "$DEPLOY_CMD" "$JOB_NAME" \
    --image "$IMAGE" \
    --region "$GCP_REGION" \
    --project "$GCP_PROJECT" \
    --tasks 1 \
    --max-retries "$MAX_RETRIES" \
    --task-timeout "$TASK_TIMEOUT" \
    --set-secrets "$SECRETS" \
    --set-env-vars "IMAGE_DIGEST=${DIGEST}" \
    --command python \
    --args "scripts/run_benchmark.py,--help"

echo "==> Done."
echo "    Image:      $IMAGE"
echo "    Digest:     $DIGEST"
echo "    Job:        $JOB_NAME (region $GCP_REGION)"
echo
echo "Next:  ./cluster/run_job.sh --exp-name <name> --dataset locomo --baseline gpt-4-turbo"

#!/usr/bin/env bash
# Build and push the memory-mcp-benchmark Docker image to GCP Artifact Registry.
# This image runs scripts/run_mcp_benchmark.py (MCP memory baselines on an
# agentic harness, e.g. claude-code + memory_md_mcp).
#
# Single image, single env ("dev"). Tags as :latest by default — Cloud Run
# Jobs re-pulls on next execution. Pass IMAGE_TAG=<sha> for an immutable tag.
#
# Usage:
#   ./build_and_push.sh                                         # :latest
#   IMAGE_TAG=$(git rev-parse --short HEAD) ./build_and_push.sh # tagged
#
# Prereqs:
#   - Docker authenticated to AR:
#       gcloud auth configure-docker us-east1-docker.pkg.dev
#   - Artifact Registry repo `pam-dev-cloud-run-jobs` exists in
#     harmix-pam-dev (us-east1).

set -euo pipefail

REGISTRY="europe-west1-docker.pkg.dev/harmix-pam-dev/pam-dev-cloud-run-jobs"
IMAGE_NAME="memory-mcp-benchmark"
IMAGE_TAG="${IMAGE_TAG:-latest}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

IMAGE="$REGISTRY/$IMAGE_NAME:$IMAGE_TAG"

echo ">>> building $IMAGE"
docker build --platform linux/amd64 \
  -f "$SCRIPT_DIR/Dockerfile" \
  -t "$IMAGE" \
  "$REPO_ROOT"

echo ">>> pushing $IMAGE"
docker push "$IMAGE"

DIGEST="$(docker inspect --format='{{index .RepoDigests 0}}' "$IMAGE" 2>/dev/null || true)"

echo ""
echo "Done."
echo "  Image:  $IMAGE"
[[ -n "$DIGEST" ]] && echo "  Digest: $DIGEST"

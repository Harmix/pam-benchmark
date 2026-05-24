#!/usr/bin/env bash
# Execute the Cloud Run Job once with the given benchmark args.
#
# Env vars:
#   GCP_PROJECT          GCP project id
#   GCP_REGION           e.g. europe-west1
#   JOB_NAME             (default: pam-benchmark)
#   WAIT                 if "true", block until job completes (default: true)
#
# Usage:
#   ./cluster/run_job.sh --exp-name locomo_gpt4_full --dataset locomo --baseline gpt-4-turbo
#   ./cluster/run_job.sh --exp-name smoke --dataset locomo --baseline gpt-4-turbo --max-questions 5 --sample-index 0

set -euo pipefail

: "${GCP_PROJECT:?must set GCP_PROJECT}"
: "${GCP_REGION:?must set GCP_REGION}"

JOB_NAME="${JOB_NAME:-pam-benchmark}"
WAIT="${WAIT:-true}"

if [[ $# -eq 0 ]]; then
    cat <<EOF
Usage: $0 <run_benchmark.py args...>
Example:
  $0 --exp-name smoke --dataset locomo --baseline gpt-4-turbo --max-questions 5 --sample-index 0
EOF
    exit 1
fi

# Build the comma-separated --args list that Cloud Run Jobs expects.
# Args with commas inside would need additional escaping; baseline kwargs
# JSON has no commas in practice (we use multiple keys at the same level).
ARGS_CSV="scripts/run_benchmark.py"
for arg in "$@"; do
    ARGS_CSV="${ARGS_CSV},${arg}"
done

# Force JSON logs so Cloud Logging gets structured entries.
ARGS_CSV="${ARGS_CSV},--log-format,json"

echo "==> Executing job: $JOB_NAME"
echo "    Args: $ARGS_CSV"

WAIT_FLAG=""
[[ "$WAIT" == "true" ]] && WAIT_FLAG="--wait"

gcloud run jobs execute "$JOB_NAME" \
    --region "$GCP_REGION" \
    --project "$GCP_PROJECT" \
    --update-env-vars "FORCE_RERUN=$(date +%s)" \
    --args "$ARGS_CSV" \
    $WAIT_FLAG

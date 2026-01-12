#!/usr/bin/env bash

set -e  # Exit immediately if a command fails

ENV_FILE=".env"

if [ ! -f "$ENV_FILE" ]; then
  echo "Error: $ENV_FILE file not found."
  exit 1
fi

# Export variables from .env (ignores comments and empty lines)
export $(grep -v '^#' "$ENV_FILE" | xargs)

# Run the command
harbor tasks start-env -p benchmark -e docker -a -i

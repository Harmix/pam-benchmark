#!/bin/bash
set -e

# Simple entrypoint that delegates to Python startup script
exec python /app/docker-startup.py "$@"
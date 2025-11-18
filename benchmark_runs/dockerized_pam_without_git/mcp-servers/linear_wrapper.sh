#!/bin/bash
export PYTHONPATH="/mcp-servers:$PYTHONPATH"
exec python3 /mcp-servers/slack_mcp_server.py "$@"
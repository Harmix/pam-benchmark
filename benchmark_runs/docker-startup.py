#!/usr/bin/env python3
"""
Docker startup script for MCP servers with data loading
"""

import sys
import os
from pathlib import Path

# Get configuration from environment or arguments
SERVER_TYPE = sys.argv[1] if len(sys.argv) > 1 else "both"
CONFIG_NAME = sys.argv[2] if len(sys.argv) > 2 else os.getenv("CONFIG_NAME", "config_1")
dev_mode = os.getenv("MCP_DEV_MODE", "false").lower() == "true"


print("=" * 40)
print("MCP Server Startup")
print("=" * 40)
print(f"Server Type: {SERVER_TYPE}")
print(f"Config: {CONFIG_NAME}")
print("=" * 40)

# Check if config exists
config_path = Path(f"test_configs/{CONFIG_NAME}.yaml")
event_name = CONFIG_NAME.replace("config_", "event_history_")
event_path = Path(f"test_event_histories/{event_name}.json")

if not config_path.exists():
    print(f"ERROR: Config file not found: {config_path}")
    print("\nAvailable configs:")
    for cfg in sorted(Path("test_configs").glob("*.yaml")):
        print(f"  - {cfg.stem}")
    sys.exit(1)

if not event_path.exists():
    print(f"WARNING: Event history not found: {event_path}")
    print("Server will start with config data only")

print()
print("Loading data from:")
print(f"  Config: {config_path}")
print(f"  Events: {event_path}")
print()

# Import modules
from data_loader import MCPDataLoader

def load_and_start_slack():
    """Load data and start Slack MCP server"""
    import slack_mcp_server

    print("Loading Slack data...")
    try:
        loader = MCPDataLoader(str(config_path), str(event_path))
        loader.initialize_slack_from_config(slack_mcp_server)
        if event_path.exists():
            loader.load_event_history()
            loader.load_events_into_servers(None, slack_mcp_server)

        print(f"✓ Loaded {len(slack_mcp_server.MESSAGES)} messages")
        print(f"✓ Loaded {len(slack_mcp_server.CHANNELS)} channels")
        print(f"✓ Loaded {len(slack_mcp_server.USERS)} users")
    except Exception as e:
        print(f"Warning: Could not load data: {e}")
        import traceback
        traceback.print_exc()

    print("\nStarting Slack MCP server...")
    if dev_mode:
        print("\nStarting Slack MCP server in DEV mode...")
        slack_mcp_server.mcp.run(transport='sse')
    else:
        print("\nStarting Slack MCP server...")
        slack_mcp_server.mcp.run(debug=True)

def load_and_start_linear():
    """Load data and start Linear MCP server"""
    import linear_mcp_server

    print("Loading Linear data...")
    try:
        loader = MCPDataLoader(str(config_path), str(event_path))
        loader.initialize_linear_from_config(linear_mcp_server)
        if event_path.exists():
            loader.load_event_history()
            loader.load_events_into_servers(linear_mcp_server, None)

        print(f"✓ Loaded {len(linear_mcp_server.TICKETS)} tickets")
        print(f"✓ Loaded {len(linear_mcp_server.TEAMS)} teams")
        print(f"✓ Loaded {len(linear_mcp_server.MILESTONES)} milestones")
    except Exception as e:
        print(f"Warning: Could not load data: {e}")
        import traceback
        traceback.print_exc()

    print("\nStarting Linear MCP server...")
    linear_mcp_server.mcp.run(debug=True)

def load_both():
    """Load data for both servers"""
    import linear_mcp_server
    import slack_mcp_server

    print("Loading data for both servers...")
    try:
        loader = MCPDataLoader(str(config_path), str(event_path))
        loader.load_all(linear_mcp_server, slack_mcp_server)
        print("\n✓ Data loaded successfully")
        print(f"  Linear: {len(linear_mcp_server.TICKETS)} tickets")
        print(f"  Slack: {len(slack_mcp_server.MESSAGES)} messages")
    except Exception as e:
        print(f"Warning: Could not load data: {e}")
        import traceback
        traceback.print_exc()

    print("\nBoth servers initialized.")
    print("Note: Servers are loaded but not running.")
    print("Use docker-compose to run them separately.")

    # Keep container running
    import time
    while True:
        time.sleep(3600)

# Start appropriate server
if SERVER_TYPE == "slack":
    load_and_start_slack()
elif SERVER_TYPE == "linear":
    load_and_start_linear()
elif SERVER_TYPE == "both":
    load_both()
else:
    print(f"ERROR: Invalid server type: {SERVER_TYPE}")
    print("Valid options: slack, linear, both")
    sys.exit(1)
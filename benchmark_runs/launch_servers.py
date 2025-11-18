"""
Unified launcher for Linear and Slack MCP servers with data loading
"""

import sys
import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="Launch Linear and Slack MCP servers with test data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python launch_servers.py config_1
  python launch_servers.py config_vg_15
  python launch_servers.py --config test_configs/config_1.yaml --events test_event_histories/event_history_1.json
        """
    )

    parser.add_argument(
        "config_name",
        nargs="?",
        help="Config name (e.g., 'config_1' or 'config_vg_15')"
    )

    parser.add_argument(
        "--config",
        help="Full path to config YAML file"
    )

    parser.add_argument(
        "--events",
        help="Full path to event history JSON file"
    )

    parser.add_argument(
        "--server",
        choices=["linear", "slack", "both"],
        default="both",
        help="Which server(s) to launch (default: both)"
    )

    parser.add_argument(
        "--list",
        action="store_true",
        help="List available configs and exit"
    )

    args = parser.parse_args()

    # Handle --list option
    if args.list:
        list_available_configs()
        return

    # Determine config and event paths
    if args.config and args.events:
        config_path = args.config
        event_path = args.events
    elif args.config_name:
        try:
            from data_loader import find_matching_files
            config_path, event_path = find_matching_files(args.config_name)
            print(f"Using config: {config_path}")
            print(f"Using events: {event_path}")
        except FileNotFoundError as e:
            print(f"Error: {e}")
            print("\nRun with --list to see available configs")
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)

    # Load data
    try:
        from data_loader import MCPDataLoader

        loader = MCPDataLoader(config_path, event_path)
        print("\n" + "="*60)
        print("Loading test data...")
        print("="*60)

        # Import servers
        if args.server in ["linear", "both"]:
            import linear_mcp_server

        if args.server in ["slack", "both"]:
            import slack_mcp_server

        # Load all data
        if args.server == "both":
            loader.load_all(linear_mcp_server, slack_mcp_server)
        elif args.server == "linear":
            loader.load_config()
            loader.load_event_history()
            loader.initialize_linear_from_config(linear_mcp_server)
            loader.load_events_into_servers(linear_mcp_server, None)
        elif args.server == "slack":
            loader.load_config()
            loader.load_event_history()
            loader.initialize_slack_from_config(slack_mcp_server)
            loader.load_events_into_servers(None, slack_mcp_server)

        print("\n" + "="*60)
        print("Data loading complete!")
        print("="*60)
        print("\nServers are ready to use.")
        print("Note: In production, servers would be launched separately.")
        print("This script demonstrates data loading functionality.\n")

    except Exception as e:
        print(f"\nError loading data: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def list_available_configs():
    """List all available config files"""
    config_dir = Path("test_configs")

    if not config_dir.exists():
        print("test_configs directory not found")
        return

    configs = sorted(config_dir.glob("config_*.yaml"))

    if not configs:
        print("No config files found in test_configs/")
        return

    print("\nAvailable configs:")
    print("="*60)

    # Group configs
    regular = []
    crisis = []
    pw = []
    vg = []

    for config in configs:
        name = config.stem
        if "crisis" in name:
            crisis.append(name)
        elif "_pw_" in name:
            pw.append(name)
        elif "_vg_" in name:
            vg.append(name)
        else:
            regular.append(name)

    if regular:
        print("\nRegular configs:")
        for name in regular:
            print(f"  {name}")

    if crisis:
        print("\nCrisis configs:")
        for name in crisis:
            print(f"  {name}")

    if pw:
        print("\nPW configs:")
        for name in pw:
            print(f"  {name}")

    if vg:
        print(f"\nVG configs: ({len(vg)} total)")
        for name in vg[:5]:
            print(f"  {name}")
        if len(vg) > 5:
            print(f"  ... and {len(vg) - 5} more")

    print("\n" + "="*60)
    print(f"Total: {len(configs)} configs\n")


if __name__ == "__main__":
    main()
"""
Test script to verify data loader functionality
"""

import sys
from pathlib import Path


def test_data_loader():
    """Test the data loader with sample data"""
    print("="*60)
    print("Testing Data Loader")
    print("="*60)

    # Test 1: Find matching files
    print("\n[TEST 1] Finding matching files...")
    try:
        from data_loader import find_matching_files

        config_path, event_path = find_matching_files("config_1")
        print(f"✓ Found config: {config_path}")
        print(f"✓ Found events: {event_path}")
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

    # Test 2: Load config file
    print("\n[TEST 2] Loading config file...")
    try:
        from data_loader import MCPDataLoader

        loader = MCPDataLoader(config_path, event_path)
        config = loader.load_config()

        linear_config = config.get('linear', {})
        teams = linear_config.get('teams', [])
        milestones = linear_config.get('milestones', [])

        print(f"✓ Loaded config with {len(teams)} teams")
        print(f"✓ Found {len(milestones)} milestones")
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

    # Test 3: Load event history
    print("\n[TEST 3] Loading event history...")
    try:
        events = loader.load_event_history()

        linear_events = [e for e in events if e.get('platform') == 'linear']
        slack_events = [e for e in events if e.get('platform') == 'slack']

        print(f"✓ Loaded {len(events)} total events")
        print(f"  - Linear events: {len(linear_events)}")
        print(f"  - Slack events: {len(slack_events)}")
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

    # Test 4: Initialize Linear server
    print("\n[TEST 4] Initializing Linear server...")
    try:
        import linear_mcp_server

        # Store original state
        original_teams = len(linear_mcp_server.TEAMS)
        original_milestones = len(linear_mcp_server.MILESTONES)

        loader.initialize_linear_from_config(linear_mcp_server)

        print(f"✓ Initialized {len(linear_mcp_server.TEAMS)} teams (was {original_teams})")
        print(f"✓ Initialized {len(linear_mcp_server.MILESTONES)} milestones (was {original_milestones})")

        # Show teams
        for team_name, team_data in linear_mcp_server.TEAMS.items():
            print(f"  - Team '{team_name}': {len(team_data['members'])} members")
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Test 5: Initialize Slack server
    print("\n[TEST 5] Initializing Slack server...")
    try:
        import slack_mcp_server

        original_users = len(slack_mcp_server.USERS)
        original_channels = len(slack_mcp_server.CHANNELS)

        loader.initialize_slack_from_config(slack_mcp_server)

        print(f"✓ Initialized {len(slack_mcp_server.USERS)} users (was {original_users})")
        print(f"✓ Initialized {len(slack_mcp_server.CHANNELS)} channels (was {original_channels})")
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Test 6: Load events into servers
    print("\n[TEST 6] Loading events into servers...")
    try:
        loader.load_events_into_servers(linear_mcp_server, slack_mcp_server)

        print(f"✓ Linear tickets: {len(linear_mcp_server.TICKETS)}")
        print(f"✓ Slack messages: {len(slack_mcp_server.MESSAGES)}")

        # Show some ticket stats
        if linear_mcp_server.TICKETS:
            statuses = {}
            for ticket in linear_mcp_server.TICKETS.values():
                status = ticket['status']
                statuses[status] = statuses.get(status, 0) + 1

            print("\n  Ticket status breakdown:")
            for status, count in sorted(statuses.items()):
                print(f"    - {status}: {count}")
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

    # Test 7: Verify data integrity
    print("\n[TEST 7] Verifying data integrity...")
    try:
        # Check that all tickets have required fields
        for ticket_id, ticket in linear_mcp_server.TICKETS.items():
            assert 'title' in ticket
            assert 'team' in ticket
            assert 'status' in ticket
            assert 'created_at' in ticket

        print(f"✓ All {len(linear_mcp_server.TICKETS)} tickets have required fields")

        # Check that all messages have required fields
        for msg in slack_mcp_server.MESSAGES:
            assert 'id' in msg
            assert 'timestamp' in msg
            assert 'text' in msg

        print(f"✓ All {len(slack_mcp_server.MESSAGES)} messages have required fields")
    except AssertionError as e:
        print(f"✗ Data integrity check failed: {e}")
        return False

    print("\n" + "="*60)
    print("All tests passed! ✓")
    print("="*60)
    return True


def test_with_custom_config():
    """Test with a specific config if provided"""
    if len(sys.argv) > 1:
        config_name = sys.argv[1]
        print(f"\nTesting with config: {config_name}")

        try:
            from data_loader import find_matching_files, MCPDataLoader

            config_path, event_path = find_matching_files(config_name)
            loader = MCPDataLoader(config_path, event_path)

            import linear_mcp_server
            import slack_mcp_server

            loader.load_all(linear_mcp_server, slack_mcp_server)

            print(f"\n✓ Successfully loaded {config_name}")
            print(f"  Linear: {len(linear_mcp_server.TICKETS)} tickets")
            print(f"  Slack: {len(slack_mcp_server.MESSAGES)} messages")

        except Exception as e:
            print(f"\n✗ Failed to load {config_name}: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    print("\n" + "="*60)
    print("MCP Data Loader Test Suite")
    print("="*60)

    # Run main test with config_1
    if test_data_loader():
        # If a specific config was provided, test it
        if len(sys.argv) > 1:
            test_with_custom_config()
    else:
        print("\n✗ Tests failed")
        sys.exit(1)
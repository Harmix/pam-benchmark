"""
Slack MCP Server Mock Implementation with Data Loading Support
Provides in-memory mock Slack functionality for testing
"""

from datetime import datetime
from typing import Optional
from fastmcp import FastMCP
import sys

# In-memory storage
CHANNELS = {
#     "general": {"id": "C001", "name": "general", "members": ["alice", "bob", "charlie"]},
#     "random": {"id": "C002", "name": "random", "members": ["alice", "bob", "dave"]},
#     "engineering": {"id": "C003", "name": "engineering", "members": ["alice", "charlie", "eve"]},
}

USERS = {
#     "alice": {"id": "U001", "name": "alice", "real_name": "Alice Smith", "status": "online"},
#     "bob": {"id": "U002", "name": "bob", "real_name": "Bob Johnson", "status": "away"},
#     "charlie": {"id": "U003", "name": "charlie", "real_name": "Charlie Brown", "status": "online"},
#     "dave": {"id": "U004", "name": "dave", "real_name": "Dave Wilson", "status": "offline"},
#     "eve": {"id": "U005", "name": "eve", "real_name": "Eve Martinez", "status": "online"},
}

MESSAGES = []
MESSAGE_ID_COUNTER = 0
UNREAD_MARKERS = {}

# Create server
mcp = FastMCP("slack-mock")

def get_next_message_id():
    global MESSAGE_ID_COUNTER
    msg_id = f"M{MESSAGE_ID_COUNTER:04d}"
    MESSAGE_ID_COUNTER += 1
    return msg_id


@mcp.tool
def get_unread_messages(limit: int = 50) -> str:
    """
    Retrieve unread messages grouped by channel/DM, automatically marked as read after retrieval.

    Args:
        limit: Maximum number of messages to retrieve (default: 50)

    Returns:
        Formatted string with unread messages grouped by channel/DM
    """
    unread_messages = []

    for msg in MESSAGES[-limit:]:
        msg_id = msg["id"]
        channel = msg.get("channel")
        user = msg.get("from_user")

        key = f"{channel}:{user}" if channel else f"dm:{user}"
        if key not in UNREAD_MARKERS or UNREAD_MARKERS[key] < msg_id:
            unread_messages.append(msg)
            UNREAD_MARKERS[key] = msg_id

    if not unread_messages:
        return "No unread messages."

    grouped = {}
    for msg in unread_messages:
        key = msg.get("channel", f"DM with {msg['from_user']}")
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(msg)

    result = []
    for key, msgs in grouped.items():
        result.append(f"\n## {key}\n")
        for msg in msgs:
            timestamp = msg.get("timestamp", "")
            from_user = msg.get("from_user", "unknown")
            text = msg.get("text", "")
            result.append(f"[{timestamp}] @{from_user}: {text}")

    return "\n".join(result)


@mcp.tool
def send_channel_message(channel: str, message: str) -> str:
    """
    Send message to a channel with @username mention support.

    Args:
        channel: Channel name (e.g., "general", "engineering")
        message: Message text with optional @username mentions

    Returns:
        Confirmation of message sent
    """
    if channel not in CHANNELS:
        return f"Error: Channel '{channel}' not found. Available channels: {', '.join(CHANNELS.keys())}"

    msg_id = get_next_message_id()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    MESSAGES.append({
        "id": msg_id,
        "channel": channel,
        "from_user": "current_user",
        "text": message,
        "timestamp": timestamp,
        "type": "channel"
    })

    return f"Message sent to #{channel} (ID: {msg_id})"


@mcp.tool
def send_direct_message(to_user: str, message: str) -> str:
    """
    Send direct message to another user.

    Args:
        to_user: Username to send DM to
        message: Message text

    Returns:
        Confirmation of DM sent
    """
    if to_user not in USERS:
        return f"Error: User '{to_user}' not found. Available users: {', '.join(USERS.keys())}"

    msg_id = get_next_message_id()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    MESSAGES.append({
        "id": msg_id,
        "from_user": "current_user",
        "to_user": to_user,
        "text": message,
        "timestamp": timestamp,
        "type": "dm"
    })

    return f"Direct message sent to @{to_user} (ID: {msg_id})"


@mcp.tool
def get_channel_messages(channel: str, limit: int = 50, after_id: Optional[str] = None) -> str:
    """
    Retrieve channel messages with pagination support.

    Args:
        channel: Channel name
        limit: Maximum number of messages (default: 50)
        after_id: Message ID to start after for pagination

    Returns:
        Formatted channel message history
    """
    if channel not in CHANNELS:
        return f"Error: Channel '{channel}' not found."

    channel_msgs = [m for m in MESSAGES if m.get("channel") == channel]

    if after_id:
        try:
            start_idx = next(i for i, m in enumerate(channel_msgs) if m["id"] == after_id) + 1
            channel_msgs = channel_msgs[start_idx:]
        except StopIteration:
            return f"Error: Message ID '{after_id}' not found in channel."

    channel_msgs = channel_msgs[-limit:]

    if not channel_msgs:
        return f"No messages in #{channel}."

    result = [f"Messages in #{channel}:\n"]
    for msg in channel_msgs:
        timestamp = msg.get("timestamp", "")
        from_user = msg.get("from_user", "unknown")
        text = msg.get("text", "")
        msg_id = msg.get("id", "")
        result.append(f"[{timestamp}] @{from_user} ({msg_id}): {text}")

    return "\n".join(result)


@mcp.tool
def get_direct_messages(with_user: str, limit: int = 50, after_id: Optional[str] = None) -> str:
    """
    Retrieve DM conversation history with pagination.

    Args:
        with_user: Username to get DM history with
        limit: Maximum number of messages (default: 50)
        after_id: Message ID to start after for pagination

    Returns:
        Formatted DM conversation history
    """
    if with_user not in USERS:
        return f"Error: User '{with_user}' not found."

    dm_msgs = [
        m for m in MESSAGES
        if m.get("type") == "dm" and (
            (m.get("from_user") == with_user and m.get("to_user") == "current_user") or
            (m.get("to_user") == with_user and m.get("from_user") == "current_user")
        )
    ]

    if after_id:
        try:
            start_idx = next(i for i, m in enumerate(dm_msgs) if m["id"] == after_id) + 1
            dm_msgs = dm_msgs[start_idx:]
        except StopIteration:
            return f"Error: Message ID '{after_id}' not found in DM history."

    dm_msgs = dm_msgs[-limit:]

    if not dm_msgs:
        return f"No DM history with @{with_user}."

    result = [f"DM conversation with @{with_user}:\n"]
    for msg in dm_msgs:
        timestamp = msg.get("timestamp", "")
        from_user = msg.get("from_user", "unknown")
        text = msg.get("text", "")
        msg_id = msg.get("id", "")
        result.append(f"[{timestamp}] @{from_user} ({msg_id}): {text}")

    return "\n".join(result)


@mcp.tool
def list_channels() -> str:
    """
    List all available channels in workspace.

    Returns:
        List of channels with member counts
    """
    result = ["Available Channels:\n"]
    for name, info in CHANNELS.items():
        member_count = len(info["members"])
        members = ", ".join(info["members"])
        result.append(f"#{name} ({member_count} members: {members})")

    return "\n".join(result)


@mcp.tool
def list_users() -> str:
    """
    List all users in the Slack workspace.

    Returns:
        List of users with their status
    """
    result = ["Workspace Users:\n"]
    for username, info in USERS.items():
        real_name = info["real_name"]
        status = info["status"]
        status_emoji = "🟢" if status == "online" else "🟡" if status == "away" else "⚫"
        result.append(f"{status_emoji} @{username} - {real_name} ({status})")

    return "\n".join(result)


@mcp.tool
def send_offline_message(to_user: str, message: str) -> str:
    """
    Send offline message when away from desk.

    Args:
        to_user: Username to send offline message to
        message: Message text

    Returns:
        Confirmation of offline message queued
    """
    if to_user not in USERS:
        return f"Error: User '{to_user}' not found."

    msg_id = get_next_message_id()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    MESSAGES.append({
        "id": msg_id,
        "from_user": "current_user",
        "to_user": to_user,
        "text": f"[OFFLINE MESSAGE] {message}",
        "timestamp": timestamp,
        "type": "dm",
        "offline": True
    })

    return f"Offline message queued for @{to_user} (ID: {msg_id}). Will be delivered when they're back online."


def initialize_from_data_loader(config_path: str = 'test_configs/config_1.yaml', event_history_path: str = 'test_event_histories/event_history_1.json'):
    """
    Initialize Slack server with data from config and event history

    Args:
        config_path: Path to YAML config file
        event_history_path: Path to JSON event history file
    """
    try:
        from data_loader import MCPDataLoader
        import slack_server

        if config_path and event_history_path:
            loader = MCPDataLoader(config_path, event_history_path)
            loader.initialize_slack_from_config(slack_server)
            loader.load_events_into_servers(None, slack_server)
            print("✓ Slack server initialized with test data")
    except Exception as e:
        print(f"Warning: Could not load test data: {e}")


if __name__ == "__main__":
    # Check for data loading arguments
    if len(sys.argv) >= 3 and sys.argv[1] == "--load-data":
        config_path = sys.argv[2]
        event_history_path = sys.argv[3] if len(sys.argv) > 3 else None

        if not event_history_path:
            from data_loader import find_matching_files
            config_path, event_history_path = find_matching_files(config_path)

        initialize_from_data_loader(config_path, event_history_path)

    mcp.run()
#
# if __name__ == "__main__":
#     import os
#
#     # Auto-load data from environment or default
#     config_name = os.getenv("MCP_CONFIG", "config_1")
#
#     try:
#         from data_loader import MCPDataLoader, find_matching_files
#         import slack_mcp_server as self_module
#
#         # Find config files
#         config_path, event_path = find_matching_files(config_name)
#
#         print(f"📦 Loading data from:")
#         print(f"   Config: {config_path}")
#         print(f"   Events: {event_path}\n")
#
#         # Load data
#         loader = MCPDataLoader(str(config_path), str(event_path))
#         loader.initialize_slack_from_config(self_module)
#         loader.load_event_history()
#         loader.load_events_into_servers(None, self_module)
#
#         print(f"✓ Loaded {len(self_module.MESSAGES)} messages")
#         print(f"✓ Loaded {len(self_module.CHANNELS)} channels")
#         print(f"✓ Loaded {len(self_module.USERS)} users\n")
#
#     except Exception as e:
#         print(f"⚠️  Could not load data: {e}")
#         import traceback
#         traceback.print_exc()
#         print("Starting with empty data...\n")
#
#     # Start the server
#     mcp.run()
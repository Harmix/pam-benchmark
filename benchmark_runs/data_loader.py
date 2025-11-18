"""
Data Loader for Linear and Slack MCP Servers
Loads test data from JSON event histories and YAML configs
"""

import json
import yaml
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime


class MCPDataLoader:
    def __init__(self, config_path: str, event_history_path: str):
        """
        Initialize data loader with config and event history paths

        Args:
            config_path: Path to YAML config file
            event_history_path: Path to JSON event history file
        """
        self.config_path = Path(config_path)
        self.event_history_path = Path(event_history_path)
        self.config = None
        self.event_history = None

    def load_config(self) -> Dict[str, Any]:
        """Load YAML configuration file"""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")

        with open(self.config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        return self.config

    def load_event_history(self) -> List[Dict[str, Any]]:
        """Load JSON event history file"""
        if not self.event_history_path.exists():
            raise FileNotFoundError(f"Event history file not found: {self.event_history_path}")

        with open(self.event_history_path, 'r') as f:
            self.event_history = json.load(f)
        return self.event_history

    def initialize_linear_from_config(self, linear_module) -> None:
        """
        Initialize Linear MCP server from config

        Args:
            linear_module: The imported linear MCP module
        """
        if not self.config:
            self.load_config()

        linear_config = self.config.get('linear', {})

        # Initialize users as admin users if specified
        users = linear_config.get('users', [])
        if users:
            linear_module.ADMIN_USERS.extend(users)
            linear_module.ADMIN_USERS = list(set(linear_module.ADMIN_USERS))

        # Initialize teams
        teams = linear_config.get('teams', [])
        for team in teams:
            team_name = team.get('name')
            members = team.get('members', [])
            if team_name:
                linear_module.TEAMS[team_name] = {
                    "name": team_name,
                    "members": members
                }

        # Initialize milestones
        milestones = linear_config.get('milestones', [])
        for milestone in milestones:
            name = milestone.get('name')
            description = milestone.get('description', '')
            start_date = milestone.get('start_date', '')
            end_date = milestone.get('end_date', '')

            if name:
                milestone_id = linear_module.get_next_milestone_id()
                linear_module.MILESTONES[name] = {
                    "id": milestone_id,
                    "name": name,
                    "description": description,
                    "start_date": start_date,
                    "end_date": end_date,
                    "completion_rate": 0.0,
                    "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }

        print(f"✓ Linear initialized with {len(linear_module.TEAMS)} teams, {len(linear_module.MILESTONES)} milestones")

    def initialize_slack_from_config(self, slack_module) -> None:
        """
        Initialize Slack MCP server from config

        Args:
            slack_module: The imported slack MCP module
        """
        if not self.config:
            self.load_config()

        # Extract unique users from Linear config
        linear_config = self.config.get('linear', {})
        all_users = set()

        # Add users from teams
        teams = linear_config.get('teams', [])
        for team in teams:
            members = team.get('members', [])
            all_users.update(members)

        # Add users from explicit user list
        users = linear_config.get('users', [])
        all_users.update(users)

        # Update Slack USERS dict
        for username in all_users:
            if username not in slack_module.USERS:
                user_id = f"U{len(slack_module.USERS) + 1:03d}"
                slack_module.USERS[username] = {
                    "id": user_id,
                    "name": username,
                    "real_name": username.capitalize(),
                    "status": "online"
                }

        # Create channels based on teams
        for team in teams:
            team_name = team.get('name', '').lower()
            if team_name and team_name not in slack_module.CHANNELS:
                channel_id = f"C{len(slack_module.CHANNELS) + 1:03d}"
                slack_module.CHANNELS[team_name] = {
                    "id": channel_id,
                    "name": team_name,
                    "members": team.get('members', [])
                }

        print(f"✓ Slack initialized with {len(slack_module.USERS)} users, {len(slack_module.CHANNELS)} channels")

    def load_events_into_servers(self, linear_module, slack_module) -> None:
        """
        Load event history into Linear and Slack servers

        Args:
            linear_module: The imported linear MCP module
            slack_module: The imported slack MCP module
        """
        if not self.event_history:
            self.load_event_history()

        linear_events = 0
        slack_events = 0
        ticket_history = {}  # Track ticket updates by title

        for event in self.event_history:
            platform = event.get('platform')
            timestamp = event.get('timestamp')
            metadata = event.get('generation_meta_data', {})

            if platform == 'linear' and linear_module is not None:
                self._process_linear_event(linear_module, metadata, timestamp, ticket_history)
                linear_events += 1

            elif platform == 'slack' and slack_module is not None:
                self._process_slack_event(slack_module, metadata, timestamp)
                slack_events += 1

        # Build message based on what was loaded
        parts = []
        if linear_module is not None and linear_events > 0:
            parts.append(f"{linear_events} Linear events")
        if slack_module is not None and slack_events > 0:
            parts.append(f"{slack_events} Slack events")

        if parts:
            print(f"✓ Loaded {', '.join(parts)}")

    def _process_linear_event(self, linear_module, metadata: Dict, timestamp: str, ticket_history: Dict) -> None:
        """Process a single Linear event"""
        title = metadata.get('title')
        description = metadata.get('description', '')
        team = metadata.get('team')
        priority = metadata.get('priority', 'medium')
        lead = metadata.get('lead')
        status = metadata.get('status', 'backlog')
        start_date = metadata.get('start_date')
        expected_finish_date = metadata.get('expected_finish_date')

        # Check if this is an update to existing ticket
        ticket_key = f"{title}:{team}"

        if ticket_key in ticket_history:
            # Update existing ticket
            ticket_id = ticket_history[ticket_key]
            ticket = linear_module.TICKETS.get(ticket_id)

            if ticket:
                # Update fields that changed
                if status and ticket['status'] != status:
                    ticket['status'] = status
                if lead and ticket['lead'] != lead:
                    ticket['lead'] = lead
                if priority and ticket['priority'] != priority:
                    ticket['priority'] = priority
                if expected_finish_date and ticket.get('due_date') != expected_finish_date:
                    ticket['due_date'] = expected_finish_date

                ticket['updated_at'] = self._parse_timestamp(timestamp)
        else:
            # Create new ticket
            ticket_id = linear_module.get_next_ticket_id()
            created_at = self._parse_timestamp(timestamp)

            linear_module.TICKETS[ticket_id] = {
                "id": ticket_id,
                "title": title,
                "description": description,
                "team": team,
                "priority": priority,
                "status": status,
                "lead": lead,
                "labels": [],
                "milestone": None,
                "due_date": expected_finish_date,
                "start_date": start_date,
                "created_at": created_at,
                "updated_at": created_at,
                "created_by": lead or "system"
            }

            ticket_history[ticket_key] = ticket_id

    def _process_slack_event(self, slack_module, metadata: Dict, timestamp: str) -> None:
        """Process a single Slack event"""
        sender = metadata.get('sender', 'system')
        message = metadata.get('message', '')
        channel = metadata.get('channel')
        recipient = metadata.get('recipient')  # For DMs

        msg_id = slack_module.get_next_message_id()
        formatted_timestamp = self._parse_timestamp(timestamp)

        if channel:
            # Channel message
            slack_module.MESSAGES.append({
                "id": msg_id,
                "channel": channel,
                "from_user": sender,
                "text": message,
                "timestamp": formatted_timestamp,
                "type": "channel"
            })
        elif recipient:
            # Direct message
            slack_module.MESSAGES.append({
                "id": msg_id,
                "from_user": sender,
                "to_user": recipient,
                "text": message,
                "timestamp": formatted_timestamp,
                "type": "dm"
            })

    def _parse_timestamp(self, timestamp: str) -> str:
        """Convert timestamp format from event history to readable format"""
        try:
            # Parse format: 20241115T0900
            dt = datetime.strptime(timestamp, "%Y%m%dT%H%M")
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except:
            return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def load_all(self, linear_module, slack_module) -> None:
        """
        Load all data: config and events into both servers

        Args:
            linear_module: The imported linear MCP module
            slack_module: The imported slack MCP module
        """
        print(f"Loading config from: {self.config_path}")
        self.load_config()

        print(f"Loading event history from: {self.event_history_path}")
        self.load_event_history()

        print("\nInitializing servers...")
        self.initialize_linear_from_config(linear_module)
        self.initialize_slack_from_config(slack_module)

        print("\nLoading events...")
        self.load_events_into_servers(linear_module, slack_module)

        print("\n✓ Data loading complete!")
        print(f"  Linear: {len(linear_module.TICKETS)} tickets, {len(linear_module.TEAMS)} teams")
        print(f"  Slack: {len(slack_module.MESSAGES)} messages, {len(slack_module.CHANNELS)} channels")


def find_matching_files(config_name: str, test_configs_dir: str = "test_configs",
                        test_events_dir: str = "test_event_histories") -> tuple:
    """
    Find matching config and event history files based on config name

    Args:
        config_name: Name of the config (e.g., "config_1" or "config_vg_1")
        test_configs_dir: Directory containing config files
        test_events_dir: Directory containing event history files

    Returns:
        Tuple of (config_path, event_history_path)
    """
    config_dir = Path(test_configs_dir)
    events_dir = Path(test_events_dir)

    # Remove .yaml extension if present
    if config_name.endswith('.yaml'):
        config_name = config_name[:-5]

    # Build paths
    config_path = config_dir / f"{config_name}.yaml"

    # Derive event history name from config name
    event_name = config_name.replace('config_', 'event_history_')
    event_path = events_dir / f"{event_name}.json"

    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    if not event_path.exists():
        raise FileNotFoundError(f"Event history file not found: {event_path}")

    return str(config_path), str(event_path)


# Example usage
if __name__ == "__main__":
    import sys

    # Example: python data_loader.py config_1
    if len(sys.argv) > 1:
        config_name = sys.argv[1]
        try:
            config_path, event_path = find_matching_files(config_name)
            print(f"Found matching files:")
            print(f"  Config: {config_path}")
            print(f"  Events: {event_path}")

            # This would be used in the actual MCP server initialization
            # loader = MCPDataLoader(config_path, event_path)
            # loader.load_all(linear_module, slack_module)

        except FileNotFoundError as e:
            print(f"Error: {e}")
            sys.exit(1)
    else:
        print("Usage: python data_loader.py <config_name>")
        print("Example: python data_loader.py config_1")
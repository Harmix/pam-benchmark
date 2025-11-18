"""
Linear MCP Server Mock Implementation with Data Loading Support
Provides in-memory mock Linear functionality for testing
"""

from datetime import datetime
from typing import Optional
from fastmcp import FastMCP
import sys
from pathlib import Path

# In-memory storage
TICKETS = {}
TICKET_ID_COUNTER = 0

TEAMS = {
}

MILESTONES = {}
MILESTONE_COUNTER = 0

CURRENT_USER = "CodeAgent"
ADMIN_USERS = ["CodeAgent"]

# Create server
mcp = FastMCP("linear-mock")


def get_next_ticket_id():
    global TICKET_ID_COUNTER
    ticket_id = f"TICK-{TICKET_ID_COUNTER:04d}"
    TICKET_ID_COUNTER += 1
    return ticket_id


def get_next_milestone_id():
    global MILESTONE_COUNTER
    milestone_id = f"MILE-{MILESTONE_COUNTER:04d}"
    MILESTONE_COUNTER += 1
    return milestone_id


def is_admin():
    return CURRENT_USER in ADMIN_USERS


@mcp.tool
def create_ticket(
    title: str,
    description: str,
    team: str,
    priority: str = "medium",
    status: str = "backlog",
    lead: Optional[str] = None,
    labels: Optional[str] = None,
    milestone: Optional[str] = None,
    due_date: Optional[str] = None,
    start_date: Optional[str] = None
) -> str:
    """
    Create new ticket with comprehensive metadata.

    Args:
        title: Ticket title
        description: Ticket description
        team: Team name (ML or Engineering)
        priority: Priority level (low, medium, high, urgent) - default: medium
        status: Status (backlog, todo, in_progress, done, cancelled) - default: backlog
        lead: Assigned team member username
        labels: Comma-separated labels
        milestone: Milestone name
        due_date: Due date (YYYY-MM-DD format)
        start_date: Start date (YYYY-MM-DD format)

    Returns:
        Ticket ID and confirmation
    """
    if team not in TEAMS:
        return f"Error: Team '{team}' not found. Available teams: {', '.join(TEAMS.keys())}"

    if lead and lead not in TEAMS[team]["members"]:
        return f"Error: User '{lead}' is not a member of team '{team}'"

    if milestone and milestone not in MILESTONES:
        return f"Error: Milestone '{milestone}' not found. Available milestones: {', '.join(MILESTONES.keys())}"

    valid_priorities = ["low", "medium", "high", "urgent"]
    if priority not in valid_priorities:
        return f"Error: Invalid priority '{priority}'. Valid priorities: {', '.join(valid_priorities)}"

    valid_statuses = ["backlog", "todo", "in_progress", "done", "cancelled"]
    if status not in valid_statuses:
        return f"Error: Invalid status '{status}'. Valid statuses: {', '.join(valid_statuses)}"

    ticket_id = get_next_ticket_id()
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    TICKETS[ticket_id] = {
        "id": ticket_id,
        "title": title,
        "description": description,
        "team": team,
        "priority": priority,
        "status": status,
        "lead": lead,
        "labels": labels.split(",") if labels else [],
        "milestone": milestone,
        "due_date": due_date,
        "start_date": start_date,
        "created_at": created_at,
        "updated_at": created_at,
        "created_by": CURRENT_USER,
    }

    return f"Ticket created: {ticket_id}\nTitle: {title}\nTeam: {team}\nPriority: {priority}\nStatus: {status}"


@mcp.tool
def update_ticket(
    ticket_id: str,
    title: Optional[str] = None,
    description: Optional[str] = None,
    priority: Optional[str] = None,
    status: Optional[str] = None,
    lead: Optional[str] = None,
    labels: Optional[str] = None,
    milestone: Optional[str] = None,
    due_date: Optional[str] = None,
    start_date: Optional[str] = None
) -> str:
    """
    Update existing ticket fields with authorization checks.

    Args:
        ticket_id: Ticket ID to update
        title: New title
        description: New description
        priority: New priority (low, medium, high, urgent)
        status: New status (backlog, todo, in_progress, done, cancelled)
        lead: New assigned lead
        labels: Comma-separated labels
        milestone: Milestone name
        due_date: Due date (YYYY-MM-DD format)
        start_date: Start date (YYYY-MM-DD format)

    Returns:
        Confirmation of update
    """
    if ticket_id not in TICKETS:
        return f"Error: Ticket '{ticket_id}' not found."

    ticket = TICKETS[ticket_id]

    if not is_admin() and ticket["created_by"] != CURRENT_USER and ticket.get("lead") != CURRENT_USER:
        return f"Error: Unauthorized to update ticket '{ticket_id}'"

    updated_fields = []

    if title:
        ticket["title"] = title
        updated_fields.append(f"title: {title}")

    if description:
        ticket["description"] = description
        updated_fields.append("description")

    if priority:
        valid_priorities = ["low", "medium", "high", "urgent"]
        if priority not in valid_priorities:
            return f"Error: Invalid priority '{priority}'"
        ticket["priority"] = priority
        updated_fields.append(f"priority: {priority}")

    if status:
        valid_statuses = ["backlog", "todo", "in_progress", "done", "cancelled"]
        if status not in valid_statuses:
            return f"Error: Invalid status '{status}'"
        ticket["status"] = status
        updated_fields.append(f"status: {status}")

    if lead:
        if lead not in TEAMS[ticket["team"]]["members"]:
            return f"Error: User '{lead}' is not a member of team '{ticket['team']}'"
        ticket["lead"] = lead
        updated_fields.append(f"lead: {lead}")

    if labels:
        ticket["labels"] = labels.split(",")
        updated_fields.append(f"labels: {labels}")

    if milestone:
        if milestone not in MILESTONES:
            return f"Error: Milestone '{milestone}' not found"
        ticket["milestone"] = milestone
        updated_fields.append(f"milestone: {milestone}")

    if due_date:
        ticket["due_date"] = due_date
        updated_fields.append(f"due_date: {due_date}")

    if start_date:
        ticket["start_date"] = start_date
        updated_fields.append(f"start_date: {start_date}")

    ticket["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if not updated_fields:
        return f"No fields updated for ticket '{ticket_id}'"

    return f"Ticket '{ticket_id}' updated:\n" + "\n".join(f"  - {field}" for field in updated_fields)


@mcp.tool
def get_ticket(ticket_id: str) -> str:
    """
    Retrieve comprehensive ticket details by ID.

    Args:
        ticket_id: Ticket ID

    Returns:
        Full ticket details
    """
    if ticket_id not in TICKETS:
        return f"Error: Ticket '{ticket_id}' not found."

    ticket = TICKETS[ticket_id]

    result = [
        f"Ticket: {ticket['id']}",
        f"Title: {ticket['title']}",
        f"Description: {ticket['description']}",
        f"Team: {ticket['team']}",
        f"Status: {ticket['status']}",
        f"Priority: {ticket['priority']}",
        f"Lead: {ticket['lead'] or 'Unassigned'}",
        f"Labels: {', '.join(ticket['labels']) if ticket['labels'] else 'None'}",
        f"Milestone: {ticket['milestone'] or 'None'}",
        f"Start Date: {ticket['start_date'] or 'Not set'}",
        f"Due Date: {ticket['due_date'] or 'Not set'}",
        f"Created: {ticket['created_at']} by {ticket['created_by']}",
        f"Updated: {ticket['updated_at']}",
    ]

    return "\n".join(result)


@mcp.tool
def list_tickets(
    team: Optional[str] = None,
    status: Optional[str] = None,
    lead: Optional[str] = None,
    milestone: Optional[str] = None,
    priority: Optional[str] = None,
    start_date_from: Optional[str] = None,
    due_date_before: Optional[str] = None
) -> str:
    """
    Query tickets with filtering by team, status, lead, milestone, priority, and date ranges.

    Args:
        team: Filter by team name
        status: Filter by status
        lead: Filter by assigned lead
        milestone: Filter by milestone
        priority: Filter by priority
        start_date_from: Filter tickets starting from date (YYYY-MM-DD)
        due_date_before: Filter tickets due before date (YYYY-MM-DD)

    Returns:
        List of filtered tickets
    """
    filtered_tickets = list(TICKETS.values())

    if team:
        filtered_tickets = [t for t in filtered_tickets if t["team"] == team]

    if status:
        filtered_tickets = [t for t in filtered_tickets if t["status"] == status]

    if lead:
        filtered_tickets = [t for t in filtered_tickets if t["lead"] == lead]

    if milestone:
        filtered_tickets = [t for t in filtered_tickets if t["milestone"] == milestone]

    if priority:
        filtered_tickets = [t for t in filtered_tickets if t["priority"] == priority]

    if start_date_from:
        filtered_tickets = [t for t in filtered_tickets if t.get("start_date") and t["start_date"] >= start_date_from]

    if due_date_before:
        filtered_tickets = [t for t in filtered_tickets if t.get("due_date") and t["due_date"] <= due_date_before]

    if not filtered_tickets:
        return "No tickets found matching the criteria."

    result = [f"Found {len(filtered_tickets)} ticket(s):\n"]
    for ticket in filtered_tickets:
        result.append(
            f"{ticket['id']} - {ticket['title']} "
            f"[{ticket['team']}] [{ticket['status']}] [{ticket['priority']}] "
            f"(Lead: {ticket['lead'] or 'Unassigned'})"
        )

    return "\n".join(result)


@mcp.tool
def delete_ticket(ticket_id: str) -> str:
    """
    Permanently remove ticket (admin-only operation).

    Args:
        ticket_id: Ticket ID to delete

    Returns:
        Confirmation of deletion
    """
    if not is_admin():
        return f"Error: Admin privileges required to delete tickets."

    if ticket_id not in TICKETS:
        return f"Error: Ticket '{ticket_id}' not found."

    ticket_title = TICKETS[ticket_id]["title"]
    del TICKETS[ticket_id]

    return f"Ticket '{ticket_id}' ('{ticket_title}') has been permanently deleted."


@mcp.tool
def assign_ticket(ticket_id: str, lead: str) -> str:
    """
    Assign or reassign ticket ownership with notifications.

    Args:
        ticket_id: Ticket ID
        lead: Username to assign ticket to

    Returns:
        Confirmation of assignment
    """
    if ticket_id not in TICKETS:
        return f"Error: Ticket '{ticket_id}' not found."

    ticket = TICKETS[ticket_id]
    team = ticket["team"]

    if lead not in TEAMS[team]["members"]:
        return f"Error: User '{lead}' is not a member of team '{team}'"

    old_lead = ticket["lead"]
    ticket["lead"] = lead
    ticket["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if old_lead:
        return f"Ticket '{ticket_id}' reassigned from @{old_lead} to @{lead}. Notification sent to both users."
    else:
        return f"Ticket '{ticket_id}' assigned to @{lead}. Notification sent."


@mcp.tool
def add_team_member(team: str, member: str) -> str:
    """
    Add user to ML or Engineering team (admin-only).

    Args:
        team: Team name
        member: Username to add

    Returns:
        Confirmation of member addition
    """
    if not is_admin():
        return f"Error: Admin privileges required to add team members."

    if team not in TEAMS:
        return f"Error: Team '{team}' not found. Available teams: {', '.join(TEAMS.keys())}"

    if member in TEAMS[team]["members"]:
        return f"Error: User '{member}' is already a member of team '{team}'"

    TEAMS[team]["members"].append(member)

    return f"User '{member}' added to team '{team}'. Current members: {', '.join(TEAMS[team]['members'])}"


@mcp.tool
def remove_team_member(team: str, member: str) -> str:
    """
    Remove user from team (admin-only).

    Args:
        team: Team name
        member: Username to remove

    Returns:
        Confirmation of member removal
    """
    if not is_admin():
        return f"Error: Admin privileges required to remove team members."

    if team not in TEAMS:
        return f"Error: Team '{team}' not found."

    if member not in TEAMS[team]["members"]:
        return f"Error: User '{member}' is not a member of team '{team}'"

    TEAMS[team]["members"].remove(member)

    return f"User '{member}' removed from team '{team}'. Current members: {', '.join(TEAMS[team]['members'])}"


@mcp.tool
def list_team_members(team: Optional[str] = None) -> str:
    """
    List team membership for specified or all teams.

    Args:
        team: Team name (optional, lists all teams if not specified)

    Returns:
        Team membership information
    """
    if team:
        if team not in TEAMS:
            return f"Error: Team '{team}' not found."
        members = TEAMS[team]["members"]
        return f"Team '{team}' members ({len(members)}):\n" + "\n".join(f"  - {m}" for m in members)

    result = ["All Teams:\n"]
    for team_name, team_info in TEAMS.items():
        members = team_info["members"]
        result.append(f"\n{team_name} ({len(members)} members):")
        result.extend(f"  - {m}" for m in members)

    return "\n".join(result)


@mcp.tool
def create_milestone(
    name: str,
    description: str,
    start_date: str,
    end_date: str
) -> str:
    """
    Create project milestone with unique naming (admin-only).

    Args:
        name: Milestone name (must be unique)
        description: Milestone description
        start_date: Start date (YYYY-MM-DD format)
        end_date: End date (YYYY-MM-DD format)

    Returns:
        Confirmation of milestone creation
    """
    if not is_admin():
        return f"Error: Admin privileges required to create milestones."

    if name in MILESTONES:
        return f"Error: Milestone '{name}' already exists."

    milestone_id = get_next_milestone_id()

    MILESTONES[name] = {
        "id": milestone_id,
        "name": name,
        "description": description,
        "start_date": start_date,
        "end_date": end_date,
        "completion_rate": 0.0,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    return f"Milestone created: {milestone_id}\nName: {name}\nStart: {start_date}\nEnd: {end_date}"


@mcp.tool
def update_milestone_progress(milestone: str, completion_rate: float) -> str:
    """
    Update milestone completion and sync to associated tickets (admin-only).

    Args:
        milestone: Milestone name
        completion_rate: Completion percentage (0.0 to 1.0)

    Returns:
        Confirmation of progress update
    """
    if not is_admin():
        return f"Error: Admin privileges required to update milestone progress."

    if milestone not in MILESTONES:
        return f"Error: Milestone '{milestone}' not found."

    if not 0.0 <= completion_rate <= 1.0:
        return f"Error: Completion rate must be between 0.0 and 1.0"

    MILESTONES[milestone]["completion_rate"] = completion_rate

    associated_tickets = [t for t in TICKETS.values() if t.get("milestone") == milestone]

    return (
        f"Milestone '{milestone}' progress updated to {completion_rate * 100:.1f}%\n"
        f"Associated tickets: {len(associated_tickets)}"
    )


@mcp.tool
def list_milestones() -> str:
    """
    Retrieve all milestones with current progress status.

    Returns:
        List of all milestones with details
    """
    if not MILESTONES:
        return "No milestones found."

    result = [f"Milestones ({len(MILESTONES)}):\n"]
    for name, milestone in MILESTONES.items():
        completion = milestone["completion_rate"] * 100
        result.append(
            f"{milestone['id']} - {name}\n"
            f"  Description: {milestone['description']}\n"
            f"  Period: {milestone['start_date']} to {milestone['end_date']}\n"
            f"  Progress: {completion:.1f}%"
        )

    return "\n".join(result)


def initialize_from_data_loader(config_path: str = None, event_history_path: str = None):
    """
    Initialize Linear server with data from config and event history

    Args:
        config_path: Path to YAML config file
        event_history_path: Path to JSON event history file
    """
    try:
        from data_loader import MCPDataLoader
        import linear_server

        if config_path and event_history_path:
            loader = MCPDataLoader(config_path, event_history_path)
            loader.initialize_linear_from_config(linear_server)
            loader.load_events_into_servers(linear_server, None)
            print("✓ Linear server initialized with test data")
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
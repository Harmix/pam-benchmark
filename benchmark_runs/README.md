# Linear and Slack MCP Server Mocks

Mock implementations of Linear and Slack MCP servers for testing in Docker environments. Both servers use in-memory storage and provide all the tools specified in the requirements.

## Installation

### Option 1: Docker (Recommended)

```bash
# Build and start both servers
docker-compose up -d

# View logs
docker-compose logs -f

# Stop servers
docker-compose down
```

### Option 2: Local Installation

```bash
pip install -r requirements.txt
```

Or with uv:

```bash
uv pip install -r requirements.txt
```

## Running the Servers

### With Docker

```bash
# Start both servers
docker-compose up -d

# Start only Slack server
docker-compose up -d slack-mcp

# Start only Linear server
docker-compose up -d linear-mcp

# View logs
docker-compose logs -f slack-mcp
docker-compose logs -f linear-mcp

# Restart servers
docker-compose restart

# Stop and remove containers
docker-compose down
```

### Without Docker

#### Slack MCP Server

```bash
# Development mode with FastMCP inspector
fastmcp dev slack_mcp_server.py

# Production mode (stdio)
fastmcp run slack_mcp_server.py

# Or direct execution
python slack_mcp_server.py
```

#### Linear MCP Server

```bash
# Development mode with FastMCP inspector
fastmcp dev linear_mcp_server.py

# Production mode (stdio)
fastmcp run linear_mcp_server.py

# Or direct execution


```

## Docker Integration

### Using with Claude Code (stdio via Docker exec)

```bash
# Add Slack mock server (running in Docker)
claude mcp add --transport stdio slack-mock -- docker exec -i slack-mcp-server python slack_mcp_server.py

# Add Linear mock server (running in Docker)
claude mcp add --transport stdio linear-mock -- docker exec -i linear-mcp-server python linear_mcp_server.py
```

Remove MCPs:
```bash
claude mcp remove slack-mock
claude mcp remove linear-mock
```

### Using with Claude Desktop (stdio via Docker exec)

Add to your `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "slack-mock": {
      "type": "stdio",
      "command": "docker",
      "args": ["exec", "-i", "slack-mcp-server", "python", "slack_mcp_server.py"]
    },
    "linear-mock": {
      "type": "stdio",
      "command": "docker",
      "args": ["exec", "-i", "linear-mcp-server", "python", "linear_mcp_server.py"]
    }
  }
}
```

### Alternative: Local File Paths

If not using Docker, use direct file paths:

```json
{
  "mcpServers": {
    "slack-mock": {
      "type": "stdio",
      "command": "python",
      "args": ["/path/to/slack_mcp_server.py"]
    },
    "linear-mock": {
      "type": "stdio",
      "command": "python",
      "args": ["/path/to/linear_mcp_server.py"]
    }
  }
}
```

## Slack Tools

1. **get_unread_messages(limit=50)** - Retrieve unread messages grouped by channel/DM
2. **send_channel_message(channel, message)** - Send message to a channel with @username support
3. **send_direct_message(to_user, message)** - Send DM to another user
4. **get_channel_messages(channel, limit=50, after_id=None)** - Retrieve channel history with pagination
5. **get_direct_messages(with_user, limit=50, after_id=None)** - Retrieve DM history with pagination
6. **list_channels()** - List all available channels
7. **list_users()** - List all workspace users
8. **send_offline_message(to_user, message)** - Queue offline message

### Pre-populated Slack Data

**Channels:**
- #general (alice, bob, charlie)
- #random (alice, bob, dave)
- #engineering (alice, charlie, eve)

**Users:**
- alice (online)
- bob (away)
- charlie (online)
- dave (offline)
- eve (online)

## Linear Tools

1. **create_ticket(...)** - Create new ticket with full metadata
2. **update_ticket(ticket_id, ...)** - Update existing ticket
3. **get_ticket(ticket_id)** - Get comprehensive ticket details
4. **list_tickets(...)** - Query tickets with multiple filters
5. **delete_ticket(ticket_id)** - Delete ticket (admin-only)
6. **assign_ticket(ticket_id, lead)** - Assign/reassign ticket
7. **add_team_member(team, member)** - Add user to team (admin-only)
8. **remove_team_member(team, member)** - Remove user from team (admin-only)
9. **list_team_members(team=None)** - List team membership
10. **create_milestone(...)** - Create project milestone (admin-only)
11. **update_milestone_progress(milestone, completion_rate)** - Update milestone progress (admin-only)
12. **list_milestones()** - List all milestones

### Pre-populated Linear Data

**Teams:**
- ML (alice, charlie, eve)
- Engineering (bob, dave, charlie)

**Current User:** alice (admin)

### Ticket Fields

- title, description, team
- priority: low, medium, high, urgent
- status: backlog, todo, in_progress, done, cancelled
- lead: assigned team member
- labels: comma-separated tags
- milestone: project milestone
- due_date, start_date: YYYY-MM-DD format

## Testing

### Slack Examples

```python
# Send a message to a channel
result = await session.call_tool("send_channel_message", {
    "channel": "engineering",
    "message": "Hello @alice, check out the new feature!"
})

# Get unread messages
result = await session.call_tool("get_unread_messages", {"limit": 20})

# List available channels
result = await session.call_tool("list_channels", {})
```

### Linear Examples

```python
# Create a ticket
result = await session.call_tool("create_ticket", {
    "title": "Fix authentication bug",
    "description": "Users can't login with OAuth",
    "team": "Engineering",
    "priority": "high",
    "status": "todo",
    "lead": "bob",
    "labels": "bug,security",
    "due_date": "2025-11-15"
})

# List tickets
result = await session.call_tool("list_tickets", {
    "team": "Engineering",
    "status": "in_progress"
})

# Assign ticket
result = await session.call_tool("assign_ticket", {
    "ticket_id": "TICK-0001",
    "lead": "charlie"
})
```

## In-Memory Storage

Both servers use in-memory storage, so all data is reset when the server restarts. This is intended for testing and development purposes only.

## Docker Commands Reference

```bash
# Build images
docker-compose build

# Start servers in background
docker-compose up -d

# Start servers in foreground (see logs)
docker-compose up

# View logs
docker-compose logs
docker-compose logs -f  # Follow logs
docker-compose logs -f slack-mcp  # Follow specific service

# Stop servers
docker-compose stop

# Stop and remove containers
docker-compose down

# Rebuild and restart
docker-compose down && docker-compose up -d --build

# Execute commands in running container
docker exec -it slack-mcp-server /bin/bash
docker exec -it linear-mcp-server /bin/bash

# View resource usage
docker stats slack-mcp-server linear-mcp-server
```

## Authorization

Linear mock implements basic authorization:
- Admin user: alice
- Users can update their own tickets or tickets assigned to them
- Admins can perform all operations
- Team member operations require admin privileges

Slack mock has no authorization - all operations are permitted.

## Notes

- Message IDs are sequential: M0001, M0002, etc.
- Ticket IDs are sequential: TICK-0001, TICK-0002, etc.
- Milestone IDs are sequential: MILE-0001, MILE-0002, etc.
- All timestamps are in "YYYY-MM-DD HH:MM:SS" format
- Unread message tracking is simplified (no per-user tracking)
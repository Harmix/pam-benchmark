# Running MCP Servers Locally

## Step 1: Install Dependencies

```bash
# Install FastMCP v2
pip install fastmcp

# Or if you prefer uv (recommended)
uv pip install fastmcp
```

## Step 2: Run the Servers

You have two options for running locally:

### Option A: Using FastMCP Dev Mode (Development/Testing)

This gives you a web UI to test your servers:

```bash
# Test Slack server
fastmcp dev slack_mcp_server.py

# Test Linear server (in another terminal)
fastmcp dev linear_mcp_server.py
```

This will open a browser where you can test the tools interactively.

### Option B: Direct Execution (Stdio Mode)

For production use with Claude Desktop/Code:

```bash
# The servers run in stdio mode by default
python slack_mcp_server.py
python linear_mcp_server.py
```

### Option C: Using FastMCP Run Command

```bash
# Run Slack server
fastmcp run slack_mcp_server.py

# Run Linear server
fastmcp run linear_mcp_server.py
```

## Step 3: Connect to Claude

### For Claude Desktop

Edit your Claude Desktop config file:

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%/Claude/claude_desktop_config.json`

Add this configuration:

```json
{
  "mcpServers": {
    "slack-mock": {
      "command": "python",
      "args": ["/absolute/path/to/slack_mcp_server.py"]
    },
    "linear-mock": {
      "command": "python",
      "args": ["/absolute/path/to/linear_mcp_server.py"]
    }
  }
}
```

**Important**: Use absolute paths! Replace `/absolute/path/to/` with your actual path.

Example:
```json
{
  "mcpServers": {
    "slack-mock": {
      "command": "python",
      "args": ["/Users/v.ratushnyi-dev/Desktop/harmix/Memtrak/mcps/slack_mcp_server.py"]
    },
    "linear-mock": {
      "command": "python",
      "args": ["/Users/v.ratushnyi-dev/Desktop/harmix/Memtrak/mcps/linear_mcp_server.py"]
    }
  }
}
```

Then restart Claude Desktop.

### For Claude Code (CLI)

```bash
# Add Slack server
claude mcp add slack-mock python /absolute/path/to/slack_mcp_server.py

# Add Linear server  
claude mcp add linear-mock python /absolute/path/to/linear_mcp_server.py

# Verify they're added
claude mcp list

# Start Claude Code
claude
```

## Step 4: Test the Connection

In Claude Desktop or Claude Code, try these commands:

```
List all Slack channels
```

```
Show me the Linear teams
```

```
Send a message to #engineering saying "Testing MCP integration"
```

```
Create a Linear ticket titled "Test ticket" in the ML team
```

## Troubleshooting

### "ModuleNotFoundError: No module named 'fastmcp'"

Install FastMCP v2:

```bash
pip install fastmcp
```

### "Command not found: fastmcp"

If `fastmcp` command isn't found after installation:

```bash
# Use python -m instead
python -m fastmcp dev slack_mcp_server.py
python -m fastmcp run slack_mcp_server.py
```

Or ensure pip's bin directory is in your PATH:
```bash
# On macOS/Linux
export PATH="$HOME/.local/bin:$PATH"

# Or use uv which handles this automatically
uv run fastmcp dev slack_mcp_server.py
```

### Claude Desktop doesn't see the servers

1. Make sure you used **absolute paths** in the config
2. Verify Python is in your PATH: `which python` or `python --version`
3. Restart Claude Desktop completely (quit and reopen)
4. Check Claude Desktop logs for errors

### Finding your Python path

```bash
# On macOS/Linux
which python
which python3

# On Windows
where python
```

Use the full path in your config if `python` command doesn't work.

### Servers start but Claude can't connect

Try running the server manually first to check for errors:

```bash
cd /path/to/your/mcps
python slack_mcp_server.py
```

You should see the server waiting for input. Press Ctrl+C to stop.

## Alternative: Using UV (Recommended)

UV is faster and handles dependencies better:

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create a virtual environment and install
cd /path/to/your/mcps
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv pip install fastmcp

# Test the servers
uv run fastmcp dev slack_mcp_server.py
```

Then in your Claude config, use the venv Python:

```json
{
  "mcpServers": {
    "slack-mock": {
      "command": "/absolute/path/to/mcps/.venv/bin/python",
      "args": ["/absolute/path/to/mcps/slack_mcp_server.py"]
    }
  }
}
```

## Quick Test Script

Create `test_servers.sh`:

```bash
#!/bin/bash

echo "Testing Slack server..."
python slack_mcp_server.py &
SLACK_PID=$!
sleep 2
kill $SLACK_PID

echo "Testing Linear server..."
python linear_mcp_server.py &
LINEAR_PID=$!
sleep 2
kill $LINEAR_PID

echo "Both servers started successfully!"
```

```bash
chmod +x test_servers.sh
./test_servers.sh
```

## Next Steps

Once connected:
1. Try listing channels: `List Slack channels`
2. Send a test message: `Send "Hello" to #general`
3. Create a ticket: `Create a ticket in ML team`
4. Check the README.md for full API documentation
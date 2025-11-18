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
[LocalSetup.md](LocalSetup.md)
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

# 🐳 MCP Docker Deployment - Complete Solution

## 📋 Quick Reference

### Super Quick Start
```bash
./quickstart.sh
```

### Manual Quick Start
```bash
make build
make up
make logs
```

### Custom Config
```bash
make up CONFIG=config_vg_15
```

## 📚 Documentation Files

- **[DOCKER_README.md](computer:///mnt/user-data/outputs/DOCKER_README.md)** - Complete Docker deployment guide
- **[PROJECT_STRUCTURE.md](computer:///mnt/user-data/outputs/PROJECT_STRUCTURE.md)** - Directory structure and setup
- **[MAIN_INDEX.md](computer:///mnt/user-data/outputs/MAIN_INDEX.md)** - Main documentation index

## 🚀 Docker Files

### Core Configuration
- **[Dockerfile](computer:///mnt/user-data/outputs/Dockerfile)** - Image definition
- **[docker-compose.yml](computer:///mnt/user-data/outputs/docker-compose.yml)** - Main orchestration
- **[docker-compose.advanced.yml](computer:///mnt/user-data/outputs/docker-compose.advanced.yml)** - Advanced profiles
- **[.dockerignore](computer:///mnt/user-data/outputs/.dockerignore)** - Build exclusions
- **[.env.example](computer:///mnt/user-data/outputs/.env.example)** - Environment template

### Helper Scripts
- **[docker-entrypoint.sh](computer:///mnt/user-data/outputs/docker-entrypoint.sh)** - Container startup
- **[quickstart.sh](computer:///mnt/user-data/outputs/quickstart.sh)** - Interactive setup
- **[Makefile](computer:///mnt/user-data/outputs/Makefile)** - Convenience commands

## 🎯 Common Commands

### Using Makefile (Recommended)

```bash
# Build
make build

# Start with default config
make up

# Start with specific config
make up CONFIG=config_vg_15

# Start individual servers
make up-slack
make up-linear

# View logs
make logs
make logs-slack
make logs-linear

# Stop
make down

# Restart
make restart

# Clean up
make clean

# List available configs
make list-configs

# Shell access
make shell-slack
make shell-linear

# Run tests
make test
```

### Using docker-compose

```bash
# Build
docker-compose build

# Start with default config
docker-compose up -d

# Start with specific config
CONFIG_NAME=config_vg_15 docker-compose up -d

# Start individual services
docker-compose up -d slack-mcp
docker-compose up -d linear-mcp

# View logs
docker-compose logs -f

# Stop
docker-compose down

# Restart
docker-compose restart
```

## 📁 Required Directory Structure

```
your_project/
├── Dockerfile
├── docker-compose.yml
├── docker-entrypoint.sh
├── requirements.txt
├── .env (create from .env.example)
│
├── data_loader.py
├── linear_mcp_server.py  ← Renamed from linear_server.py
├── slack_mcp_server.py   ← Renamed from slack_server.py
├── launch_servers.py
│
├── test_configs/
│   ├── config_1.yaml
│   ├── config_vg_15.yaml
│   └── ...
│
└── test_event_histories/
    ├── event_history_1.json
    ├── event_history_vg_15.json
    └── ...
```

## 🔧 Setup Steps

### 1. Copy Files

```bash
# Core Python files (rename as needed)
cp data_loader.py ./
cp linear_server.py ./linear_mcp_server.py
cp slack_server.py ./slack_mcp_server.py
cp launch_servers.py ./

# Docker files
cp Dockerfile docker-compose.yml docker-entrypoint.sh ./
cp Makefile quickstart.sh .env.example ./

# Make scripts executable
chmod +x docker-entrypoint.sh quickstart.sh
```

### 2. Add Your Data

```bash
# Copy your configs
cp -r /path/to/test_configs ./
cp -r /path/to/test_event_histories ./
```

### 3. Configure

```bash
# Create environment file
cp .env.example .env

# Edit if needed
nano .env
```

### 4. Run

```bash
# Interactive setup
./quickstart.sh

# Or manual
make build
make up
```

## 💡 Usage Examples

### Example 1: Basic Deployment

```bash
# Setup
make build

# Start with default config
make up

# Check status
docker-compose ps

# View logs
make logs
```

### Example 2: Different Configs

```bash
# Start with config_1
make up CONFIG=config_1

# Stop and switch to config_vg_15
make down
make up CONFIG=config_vg_15

# Or restart with new config
make restart CONFIG=config_vg_15
```

### Example 3: Individual Servers

```bash
# Start only Slack
make up-slack CONFIG=config_2

# In another terminal, start Linear with different config
make up-linear CONFIG=config_vg_15
```

### Example 4: Development Workflow

```bash
# Build
make build

# Start
make up CONFIG=config_1

# Check logs
make logs-slack

# Shell into container
make shell-slack

# Inside container
python test_data_loader.py
python -c "import slack_server; print(len(slack_server.MESSAGES))"

# Exit and restart with new config
exit
make restart CONFIG=config_2
```

### Example 5: Crisis Testing

```bash
# Using advanced compose file
docker-compose -f docker-compose.advanced.yml --profile crisis up -d

# Or with Makefile
make up-crisis
```

## 🎨 Environment Variables

### Default Configuration

```bash
# .env file
CONFIG_NAME=config_1
```

### Override at Runtime

```bash
# Temporarily override
CONFIG_NAME=config_vg_15 make up

# Or
CONFIG_NAME=config_vg_15 docker-compose up -d
```

## 🔍 Verification

### Check Data Loaded

```bash
# Check Linear tickets
docker exec linear-mcp-server python -c "
import linear_server
print(f'Tickets: {len(linear_server.TICKETS)}')
print(f'Teams: {len(linear_server.TEAMS)}')
"

# Check Slack messages
docker exec slack-mcp-server python -c "
import slack_server
print(f'Messages: {len(slack_server.MESSAGES)}')
print(f'Users: {len(slack_server.USERS)}')
"
```

### Run Tests

```bash
# Using Makefile
make test

# Using docker-compose
docker-compose run --rm slack-mcp python test_data_loader.py
```

## 🐛 Troubleshooting

### Container Won't Start

```bash
# Check logs
make logs

# Check if config exists
docker-compose run --rm slack-mcp ls -la test_configs/

# Verify entrypoint
docker-compose run --rm slack-mcp cat docker-entrypoint.sh
```

### Config Not Loading

```bash
# Check environment variable
docker exec slack-mcp-server env | grep CONFIG_NAME

# List available configs
docker exec slack-mcp-server ls test_configs/

# Test config loading
docker exec slack-mcp-server python -c "
from data_loader import find_matching_files
print(find_matching_files('config_1'))
"
```

### Data Not Populated

```bash
# Shell into container
make shell-slack

# Test data loader manually
python test_data_loader.py

# Check what got loaded
python -c "
from data_loader import MCPDataLoader
import slack_server

loader = MCPDataLoader('test_configs/config_1.yaml', 'test_event_histories/event_history_1.json')
loader.load_all(None, slack_server)
print(f'Loaded {len(slack_server.MESSAGES)} messages')
"
```

## 📊 What Gets Loaded

### From Config Files (YAML)
- ✅ Linear teams and members
- ✅ Linear milestones
- ✅ Admin users
- ✅ Slack channels (auto-created)
- ✅ Slack users (auto-created)

### From Event Files (JSON)
- ✅ Linear tickets
- ✅ Ticket updates (status, lead, etc.)
- ✅ Slack messages
- ✅ Direct messages
- ✅ Full history with timestamps

## 🚦 Deployment Modes

### Development (Default)
```bash
docker-compose up -d
```
- Uses volume mounts
- Easy to update configs
- Interactive debugging

### Production
```bash
# Build with configs baked in
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```
- Configs in image
- No volume mounts
- Optimized for performance

### Testing
```bash
# Multiple configs in parallel
CONFIG_NAME=config_1 docker-compose -p test1 up -d
CONFIG_NAME=config_2 docker-compose -p test2 up -d
```

## 🎓 Best Practices

1. **Use Makefile** - Simplifies commands
2. **Mount volumes** - Easy config updates
3. **Use .env files** - Manage configs easily
4. **Check logs** - Monitor startup
5. **Test first** - Run `make test`
6. **Use health checks** - Monitor container health
7. **Set resource limits** - Prevent resource hogging
8. **Use restart policies** - Auto-recovery

## 📦 What You Get

✅ **Automatic data loading** from configs and events
✅ **Flexible deployment** - individual or combined servers
✅ **Easy config switching** - just change environment variable
✅ **Volume mounting** - update configs without rebuilding
✅ **Makefile shortcuts** - simple commands
✅ **Health checks** - monitor container status
✅ **Multiple profiles** - crisis, VG, development modes
✅ **Production-ready** - restart policies, logging, limits

## 🎯 Summary

This Docker solution allows you to:

1. **Build once** - `make build`
2. **Run with any config** - `make up CONFIG=config_name`
3. **Switch configs easily** - just restart with new CONFIG
4. **Test multiple configs** - run in parallel
5. **Deploy to production** - same images, different configs

All your test data loads automatically when containers start!

## 🔗 Related Documentation

- **Python Data Loader**: [DATA_LOADER_README.md](computer:///mnt/user-data/outputs/DATA_LOADER_README.md)
- **Usage Examples**: [USAGE_EXAMPLES.md](computer:///mnt/user-data/outputs/USAGE_EXAMPLES.md)
- **Solution Overview**: [SOLUTION_SUMMARY.md](computer:///mnt/user-data/outputs/SOLUTION_SUMMARY.md)

---

**Ready to deploy?**

```bash
./quickstart.sh
```

Or manually:

```bash
make build
make up
make logs
```

That's it! 🚀

# MCP Docker Deployment Guide

Complete Docker deployment solution for Linear and Slack MCP servers with automatic config loading.

## Quick Start

### 1. Basic Usage (Recommended)

```bash
# Build images
make build

# Start both servers with default config (config_1)
make up

# View logs
make logs

# Stop servers
make down
```

### 2. Using Different Configs

```bash
# Start with specific config
make up CONFIG=config_vg_15

# Or using environment variable
CONFIG_NAME=config_vg_15 make up

# Or using docker-compose directly
CONFIG_NAME=config_vg_15 docker-compose up -d
```

### 3. Without Make

```bash
# Build
docker-compose build

# Start with default config
docker-compose up -d

# Start with specific config
CONFIG_NAME=config_vg_15 docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

## Configuration

### Environment Variables

Create a `.env` file from the example:

```bash
cp .env.example .env
```

Edit `.env`:

```bash
# Set your desired config
CONFIG_NAME=config_1
```

### Available Configs

List all available configurations:

```bash
make list-configs
```

Or manually:

```bash
ls test_configs/*.yaml
```

## Docker Compose Services

### Individual Services (Default)

```yaml
services:
  slack-mcp:    # Slack MCP server
  linear-mcp:   # Linear MCP server
```

**Usage:**

```bash
# Start both
docker-compose up -d

# Start only Slack
docker-compose up -d slack-mcp

# Start only Linear
docker-compose up -d linear-mcp
```

### Combined Service (Development)

```yaml
services:
  mcp-combined:  # Both servers in one container
```

**Usage:**

```bash
# Using docker-compose
docker-compose --profile combined up -d mcp-combined

# Using Makefile
make up-combined
```

## Usage Examples

### Example 1: Default Config

```bash
make build
make up
make logs
```

### Example 2: Specific Config

```bash
# Using Makefile
make up CONFIG=config_vg_15

# Using docker-compose
CONFIG_NAME=config_vg_15 docker-compose up -d

# Using environment file
echo "CONFIG_NAME=config_vg_15" > .env
docker-compose up -d
```

### Example 3: Individual Servers

```bash
# Start only Slack with config_2
CONFIG_NAME=config_2 docker-compose up -d slack-mcp

# Start only Linear with config_vg_1
CONFIG_NAME=config_vg_1 docker-compose up -d linear-mcp
```

### Example 4: Crisis Configs

```bash
# Start all crisis configs (using advanced compose)
make up-crisis

# Or manually
docker-compose -f docker-compose.advanced.yml --profile crisis up -d
```

### Example 5: Development Workflow

```bash
# Build
make build

# Start with test config
make up CONFIG=config_1

# Check logs
make logs-slack
make logs-linear

# Shell into container
make shell-slack

# Inside container, test data loading
python test_data_loader.py

# Exit and restart with different config
make down
make up CONFIG=config_vg_15
```

### Example 6: Multiple Configs (Testing)

```bash
# Terminal 1: config_1
CONFIG_NAME=config_1 docker-compose -p mcp_1 up

# Terminal 2: config_2
CONFIG_NAME=config_2 docker-compose -p mcp_2 up

# Terminal 3: config_vg_15
CONFIG_NAME=config_vg_15 docker-compose -p mcp_3 up
```

## Makefile Commands

### Basic Commands

| Command | Description |
|---------|-------------|
| `make build` | Build Docker images |
| `make up` | Start servers with default config |
| `make down` | Stop all servers |
| `make logs` | View logs from all servers |
| `make restart` | Restart servers |
| `make clean` | Remove containers and images |

### Server-Specific Commands

| Command | Description |
|---------|-------------|
| `make up-slack` | Start only Slack server |
| `make up-linear` | Start only Linear server |
| `make up-combined` | Start combined server |
| `make logs-slack` | View Slack logs |
| `make logs-linear` | View Linear logs |

### Development Commands

| Command | Description |
|---------|-------------|
| `make shell-slack` | Shell into Slack container |
| `make shell-linear` | Shell into Linear container |
| `make test` | Run tests in container |
| `make status` | Show container status |
| `make list-configs` | List available configs |

### Profile Commands

| Command | Description |
|---------|-------------|
| `make up-crisis` | Start crisis configs |
| `make up-vg` | Start VG configs |

## Docker Architecture

### Container Structure

```
┌─────────────────────────────────────┐
│         Docker Container            │
├─────────────────────────────────────┤
│  Entrypoint: docker-entrypoint.sh   │
│           ↓                          │
│  Loads: CONFIG_NAME environment var │
│           ↓                          │
│  Reads: test_configs/*.yaml         │
│          test_event_histories/*.json│
│           ↓                          │
│  Initializes: data_loader.py        │
│           ↓                          │
│  Starts: slack_mcp_server.py or     │
│          linear_mcp_server.py       │
└─────────────────────────────────────┘
```

### Volume Mounts

By default, configs are mounted as read-only:

```yaml
volumes:
  - ./test_configs:/app/test_configs:ro
  - ./test_event_histories:/app/test_event_histories:ro
```

This allows you to update configs without rebuilding images.

## Advanced Usage

### Custom Dockerfile

If you need to customize the Docker image:

```dockerfile
FROM python:3.11-slim

# Your customizations here
RUN apt-get update && apt-get install -y some-package

# Continue with standard setup
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# ... rest of Dockerfile
```

### Multiple Compose Files

Use multiple compose files for different scenarios:

```bash
# Development
docker-compose -f docker-compose.yml up

# Production
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up

# Testing with crisis configs
docker-compose -f docker-compose.advanced.yml --profile crisis up
```

### Health Checks

Containers include health checks:

```bash
# Check health status
docker ps

# View health check logs
docker inspect slack-mcp-server | grep -A 10 Health
```

### Networking

Containers communicate via `mcp-network`:

```bash
# List network
docker network ls | grep mcp

# Inspect network
docker network inspect mcp-network
```

## Troubleshooting

### Container Won't Start

```bash
# Check logs
docker-compose logs slack-mcp

# Check if config exists
docker-compose run --rm slack-mcp ls -la test_configs/

# Verify config name
docker-compose run --rm slack-mcp cat test_configs/config_1.yaml
```

### Config Not Found

```bash
# List available configs in container
docker-compose run --rm slack-mcp ls -1 test_configs/

# Check mounted volumes
docker-compose run --rm slack-mcp ls -la /app/
```

### Data Not Loading

```bash
# Shell into container
make shell-slack

# Inside container, test manually
python -c "from data_loader import find_matching_files; print(find_matching_files('config_1'))"

# Run test suite
python test_data_loader.py
```

### Port Conflicts

If ports 8000/8001 are in use:

```yaml
# Edit docker-compose.yml
services:
  slack-mcp:
    ports:
      - "8002:8000"  # Change external port
```

### View Environment Variables

```bash
# Check what config is loaded
docker exec slack-mcp-server env | grep CONFIG_NAME
```

## Production Deployment

### Best Practices

1. **Use specific config names**:
   ```bash
   CONFIG_NAME=config_prod docker-compose up -d
   ```

2. **Pin image versions**:
   ```yaml
   image: mcp-servers:1.0.0
   ```

3. **Use health checks**:
   ```yaml
   healthcheck:
     test: ["CMD", "python", "-c", "import sys; sys.exit(0)"]
   ```

4. **Set resource limits**:
   ```yaml
   deploy:
     resources:
       limits:
         cpus: '0.5'
         memory: 512M
   ```

5. **Use restart policies**:
   ```yaml
   restart: unless-stopped
   ```

### Example Production Compose

```yaml
version: '3.8'

services:
  slack-mcp:
    image: mcp-servers:${VERSION:-latest}
    environment:
      - CONFIG_NAME=${CONFIG_NAME:-config_prod}
    restart: always
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 1G
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Build and Deploy MCP Servers

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      
      - name: Build Docker image
        run: docker-compose build
      
      - name: Run tests
        run: |
          docker-compose run --rm slack-mcp python test_data_loader.py
      
      - name: Deploy
        run: |
          CONFIG_NAME=config_prod docker-compose up -d
```

## Monitoring

### View Logs

```bash
# All logs
make logs

# Specific service
make logs-slack
make logs-linear

# Follow logs
docker-compose logs -f

# Last 100 lines
docker-compose logs --tail=100
```

### Container Stats

```bash
# Real-time stats
docker stats slack-mcp-server linear-mcp-server

# Using Makefile
make status
```

## Cleanup

```bash
# Stop and remove containers
make down

# Remove everything (containers, volumes, images)
make clean

# Remove dangling images
docker image prune -f

# Remove all unused resources
docker system prune -a
```

## Summary

This Docker solution provides:

✅ **Flexible config loading** - Load any config at startup
✅ **Multiple deployment modes** - Individual or combined servers
✅ **Volume mounting** - Update configs without rebuilding
✅ **Environment variables** - Easy configuration management
✅ **Makefile shortcuts** - Simple commands for common tasks
✅ **Health checks** - Monitor container health
✅ **Profile support** - Different scenarios (crisis, VG, etc.)
✅ **Production-ready** - Restart policies, resource limits

All you need to do is:

1. Place your configs in `test_configs/`
2. Place your events in `test_event_histories/`
3. Run: `make up CONFIG=your_config_name`

Done!
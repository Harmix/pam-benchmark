# MCP Data Loader - Complete Solution

## 📚 Documentation

- **[SOLUTION_SUMMARY.md](computer:///mnt/user-data/outputs/SOLUTION_SUMMARY.md)** - Start here! Overview of what was built
- **[DATA_LOADER_README.md](computer:///mnt/user-data/outputs/DATA_LOADER_README.md)** - Complete technical documentation
- **[USAGE_EXAMPLES.md](computer:///mnt/user-data/outputs/USAGE_EXAMPLES.md)** - Code examples and patterns

## 🚀 Core Files

### Main Components
- **[data_loader.py](computer:///mnt/user-data/outputs/data_loader.py)** - Core data loading engine
- **[linear_server.py](computer:///mnt/user-data/outputs/linear_server.py)** - Updated Linear MCP server
- **[slack_server.py](computer:///mnt/user-data/outputs/slack_server.py)** - Updated Slack MCP server

### Tools
- **[launch_servers.py](computer:///mnt/user-data/outputs/launch_servers.py)** - Unified launcher script
- **[test_data_loader.py](computer:///mnt/user-data/outputs/test_data_loader.py)** - Test suite

## 🎯 Quick Start

### 1. Basic Usage
```bash
# Load data from config_1
python launch_servers.py config_1
```

### 2. List Available Configs
```bash
python launch_servers.py --list
```

### 3. Run Tests
```bash
python test_data_loader.py
```

## 📁 Expected Directory Structure

```
your_project/
├── test_configs/
│   ├── config_1.yaml
│   ├── config_2.yaml
│   ├── config_vg_1.yaml
│   └── ...
├── test_event_histories/
│   ├── event_history_1.json
│   ├── event_history_2.json
│   ├── event_history_vg_1.json
│   └── ...
├── data_loader.py
├── linear_server.py
├── slack_server.py
├── launch_servers.py
└── test_data_loader.py
```

## 🔧 How It Works

1. **Config Loading**: Reads YAML config files with teams, users, milestones
2. **Event Loading**: Reads JSON event history files
3. **Server Initialization**: Sets up Linear teams/milestones and Slack users/channels
4. **Event Processing**: Creates and updates tickets and messages from event history
5. **Data Validation**: Ensures all data is properly loaded and valid

## 💡 Key Features

✅ Automatic file matching (`config_1` → `event_history_1`)
✅ Smart event processing (handles ticket updates correctly)
✅ Backward compatible (original MCP functionality preserved)
✅ Flexible loading (load one or both servers)
✅ Comprehensive error handling
✅ Full test suite included
✅ Complete documentation

## 📖 Usage Examples

### Basic
```python
from data_loader import MCPDataLoader
import linear_server
import slack_server

# Load data
loader = MCPDataLoader("test_configs/config_1.yaml", 
                      "test_event_histories/event_history_1.json")
loader.load_all(linear_server, slack_server)

# Access loaded data
print(f"Loaded {len(linear_server.TICKETS)} tickets")
print(f"Loaded {len(slack_server.MESSAGES)} messages")
```

### With Auto-Matching
```python
from data_loader import find_matching_files, MCPDataLoader

# Find matching files
config_path, event_path = find_matching_files("config_1")

# Load data
loader = MCPDataLoader(config_path, event_path)
loader.load_all(linear_server, slack_server)
```

## 🧪 Testing

```bash
# Run all tests
python test_data_loader.py

# Test specific config
python test_data_loader.py config_vg_15
```

## 🔍 What Gets Loaded

### From Config (YAML)
- Linear teams with members
- Linear milestones with dates and descriptions
- Admin users for Linear
- Slack channels (auto-created from teams)
- Slack users (auto-created from team members)

### From Event History (JSON)
- Linear tickets (creation events)
- Linear ticket updates (status, lead, priority changes)
- Slack channel messages
- Slack direct messages
- Message history with timestamps

## 📊 Data Flow

```
┌─────────────┐
│ Config YAML │──┐
└─────────────┘  │
                 ├──> MCPDataLoader ──> Linear Server (Tickets, Teams)
┌─────────────┐  │                  └──> Slack Server (Messages, Users)
│ Events JSON │──┘
└─────────────┘
```

## 🎨 Example Config

```yaml
linear:
  users:
    - "CodeAgent"
  teams:
    - name: "engineering"
      members: ["alice", "bob", "charlie"]
    - name: "ml"
      members: ["diana", "eve"]
  milestones:
    - name: "Q1 2024 Development"
      description: "Complete development tasks"
      start_date: "2024-01-01"
      end_date: "2024-03-31"
```

## 🎨 Example Event

```json
{
  "timestamp": "20241115T0900",
  "platform": "linear",
  "generation_meta_data": {
    "title": "Legacy system migration",
    "description": "Plan the migration...",
    "team": "engineering",
    "priority": "urgent",
    "lead": "alice",
    "start_date": "2024-11-15",
    "expected_finish_date": "2024-11-30",
    "status": "todo"
  }
}
```

## 🛠️ Advanced Features

- Batch processing multiple configs
- Custom event filtering
- Data export to JSON
- Integration with test frameworks
- CI/CD pipeline support
- Data validation and integrity checks

## 📦 Dependencies

```bash
pip install pyyaml fastmcp
```

## 🤝 Integration

Works with:
- pytest / unittest
- FastAPI / Flask
- CI/CD pipelines
- Benchmarking systems
- Data analysis tools

## 📝 File Descriptions

| File | Purpose |
|------|---------|
| `data_loader.py` | Core data loading engine with MCPDataLoader class |
| `linear_server.py` | Updated Linear MCP server with data loading support |
| `slack_server.py` | Updated Slack MCP server with data loading support |
| `launch_servers.py` | Unified launcher for both servers |
| `test_data_loader.py` | Comprehensive test suite |
| `DATA_LOADER_README.md` | Complete technical documentation |
| `USAGE_EXAMPLES.md` | Code examples and usage patterns |
| `SOLUTION_SUMMARY.md` | High-level solution overview |

## 🎓 Next Steps

1. **Read** [SOLUTION_SUMMARY.md](computer:///mnt/user-data/outputs/SOLUTION_SUMMARY.md) for overview
2. **Review** [DATA_LOADER_README.md](computer:///mnt/user-data/outputs/DATA_LOADER_README.md) for details
3. **Try** examples from [USAGE_EXAMPLES.md](computer:///mnt/user-data/outputs/USAGE_EXAMPLES.md)
4. **Run** `python launch_servers.py --list` to see available configs
5. **Test** with `python launch_servers.py config_1`

## 💬 Support

- Check the README files for detailed information
- Run tests to verify your setup
- Review usage examples for common patterns
- Use `--list` flag to see available configs

---

**Built by**: World-famous software architecture expert
**Purpose**: Automatic test data loading for Linear and Slack MCP servers
**Status**: Production-ready ✅

## 🚀 Quick Start - Adding Your Docker MCP Servers

### Option 1: HTTP Transport (Recommended for Docker)

If you expose your MCP servers via HTTP:

```bash
# Add Slack MCP server
claude mcp add --transport http slack-mcp http://localhost:8000

# Add Linear MCP server  
claude mcp add --transport http linear-mcp http://localhost:8001
```

### Option 2: stdio Transport (Direct Connection)

If running locally without Docker:

```bash
# Add Slack MCP server
claude mcp add --transport stdio slack-mcp -- python /path/to/slack_mcp_server.py

# Add Linear MCP server
claude mcp add --transport stdio linear-mcp -- python /path/to/linear_mcp_server.py
```

### Option 3: With Config Loading

Add servers with data loading:

```bash
# Slack with config
claude mcp add --transport stdio slack-mcp -- python /path/to/docker-startup.py slack config_2

# Linear with config
claude mcp add --transport stdio linear-mcp -- python /path/to/docker-startup.py linear config_2
```
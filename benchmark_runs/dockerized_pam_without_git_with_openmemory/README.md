# Claude Code Docker Environment

Run Claude Code in an isolated Docker container with API key authentication.

## Prerequisites

- Docker and Docker Compose installed
- Anthropic API key from [console.anthropic.com](https://console.anthropic.com/)

## Setup

1. Clone this repository and navigate to the directory

2. Create `.env` file:
```bash
ANTHROPIC_API_KEY=your-api-key-here
```

3. Build and start the container:
```bash
docker-compose up -d
```

4. Access the container:
```bash
docker-compose exec claude-code bash
```

5. Run Claude Code:
```bash
claude
```

## Project Structure
```
.
├── docker-compose.yml
├── Dockerfile
├── .env                 # Your API key (don't commit!)
└── workspace/          # Your project files go here
```

## Usage

- Place your project files in the `./workspace` directory
- They will be accessible inside the container at `/workspace`
- All changes are persisted on your host machine

## Stop Container
```bash
docker-compose down
```

## Important

- Never commit `.env` file to version control
- Add `.env` to your `.gitignore`
- API usage will be charged to your Anthropic account

## Troubleshooting

Check if API key is set correctly inside container:
```bash
docker-compose exec claude-code bash -c 'echo $ANTHROPIC_API_KEY'
```

Verify Claude Code installation:
```bash
docker-compose exec claude-code bash -c 'claude --version'
```

# Rebuild with new configs
docker-compose build --no-cache

# Start container
docker-compose up -d

# Run benchmark for config_1
docker-compose exec claude-code /workspace/setup_and_run.sh

# Connect to Container
docker-compose exec claude-code bash

# Rebuild
docker-compose down && docker-compose build && docker-compose up -d
docker-compose exec -it claude-code /workspace/setup_and_run.sh

# MCP
python3 /mcp-servers/slack_mcp_server.py /workspace/test_configs/config_1.yaml /workspace/test_event_histories/event_history_1.json 2>&1

python3 /mcp-servers/linear_mcp_server.py /workspace/test_configs/config_1.yaml /workspace/test_event_histories/event_history_1.json 2>&1

# Make scripts executable
chmod +x run_all_isolated.sh
chmod +x run_range_isolated.sh

# Build the image first
docker-compose build

# Run ALL 46 configs with full isolation
./run_all_isolated.sh

# Run specific range (e.g., configs 1-10)
./run_range_isolated.sh 1 10

# Run second half (configs 24-46)
./run_range_isolated.sh 24 46

# Run just one config
docker-compose run --rm claude-code /benchmark_data/setup_and_run.sh /benchmark_data/test_configs/config_1.yaml
```

**Directory Structure:**
```
your_project/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── data_loader.py
├── slack_mcp_server.py
├── linear_mcp_server.py
├── setup_and_run.sh
├── run_all_isolated.sh          # Host script
├── run_range_isolated.sh        # Host script
├── test_configs/
│   ├── config_1.yaml
│   ├── config_2.yaml
│   └── ... (up to config_46.yaml)
├── test_event_histories/
│   ├── event_history_1.json
│   └── ...
├── claude-config/               # Empty initially
└── outputs/                     # Results appear here


MEMORY:
```bash
chmod +x setup_openmemory.sh
./setup_openmemory.sh
```
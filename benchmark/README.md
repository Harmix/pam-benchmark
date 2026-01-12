# PAM Benchmark Harbor Task

This Harbor task structure allows you to run PAM (Proactive AI Manager) benchmark evaluations using the Harbor framework.

## Task Structure

```
benchmark/
├── instruction.md          # Task description and requirements
├── task.toml              # Harbor task configuration
├── environment/
│   └── Dockerfile        # Container environment definition
├── tests/
│   ├── test.sh           # Test verification script
│   └── test_outputs.py   # Pytest unit tests
├── test_configs/         # YAML configuration files
├── test_event_histories/ # JSON event history files
├── setup_and_run.sh      # Main execution script
├── init.py               # PAM memory structure generator
├── INIT.md               # PAM Memory Agent Guide
├── INTRO_TEMPLATE.md     # Company template
└── CLAUDE.md             # Claude Code system context
```

## Prerequisites

1. Install Harbor framework
2. Set `ANTHROPIC_API_KEY` environment variable
3. Have Docker installed and running

## Usage

### Start Interactive Environment

To start an interactive environment (similar to the original docker-compose setup):

```bash
harbor tasks start-env -p benchmark -e docker -a -i
```

This will:
- Build the Docker image from `environment/Dockerfile`
- Start an interactive container
- Mount the task files into the container
- Give you a shell to work with

### Running a Benchmark

Once inside the interactive environment, you can run benchmarks:

```bash
export ANTHROPIC_API_KEY=<YOUR-KEY>

# Run a single config
/benchmark_data/setup_and_run.sh /benchmark_data/test_configs/config_1.yaml

# Or run a range (if you have the run_range_isolated.sh script)
# Note: You may need to copy this script into the task directory if needed
```

### Running with Harbor Agent

To run with a Harbor agent (instead of interactive mode):

```bash
harbor run -p benchmark -a <agent-name> -m <model>
```

Note: The current setup is optimized for claude-code which is pre-installed in the container. You may need to configure Harbor to use the container's claude-code installation.

## Task Configuration

The task is configured in `task.toml`:
- **Timeout**: 30 minutes for both agent and verifier
- **Resources**: 2 CPUs, 4GB RAM, 20GB storage
- **Difficulty**: Hard
- **Category**: Multi-modal reasoning

## Test Configs and Event Histories

- **test_configs/**: Contains YAML files defining benchmark scenarios
- **test_event_histories/**: Contains JSON files with Linear and Slack event data

Each config file references an event history file and defines:
- Agent configuration
- Benchmark questions
- Expected answers

## Environment Details

The Docker environment includes:
- Python 3.11
- Claude Code v2.0.76 (installed globally)
- yq for YAML parsing
- System tools (curl, git, jq, build-essential, tree)

## Differences from Original Setup

The Harbor version:
- Uses Harbor's task structure instead of docker-compose
- Can be run with Harbor's agent system
- Maintains the same execution flow via `setup_and_run.sh`
- Test verification uses Harbor's standard test format

## Next Steps

1. **Solution Script**: Create a `solution/` directory with `solve.sh` for automated Oracle testing
2. **Enhanced Tests**: Update `tests/test_outputs.py` with specific verification logic for your benchmarks
3. **Agent Configuration**: Configure Harbor to use claude-code if needed for non-interactive runs


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
2. Set `ANTHROPIC_API_KEY` environment variable (required for LLM judge evaluation)
3. Have Docker installed and running
4. (Optional) Configure MongoDB for results storage:
   - Set `DB_NAME` in `benchmark/environment/secrets.env`
   - Set `CONNECTION_STRING` in `benchmark/environment/secrets.env`

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
# Run a single config
/benchmark_data/setup_and_run.sh /benchmark_data/test_configs/config_1.yaml

# Or run a range (if you have the run_range_isolated.sh script)
# Note: You may need to copy this script into the task directory if needed
```

### Running Tasks Non-Interactively with Configs

**Quick Start: Use the helper script (Recommended)**

From the project root, use the `run_benchmark.sh` script:

```bash
# Interactive mode - will prompt for configs
./run_benchmark.sh

# Or specify configs directly
./run_benchmark.sh config_1 config_2 config_3

# With Harbor arguments
./run_benchmark.sh config_1 config_2 -a oracle -m claude-3-5-sonnet-20241022
```

The script will:
- Validate that configs exist
- Create `benchmark_configs.txt` automatically
- Start Harbor with the appropriate settings

**Manual Method: Create config file**

Alternatively, create a `benchmark_configs.txt` file manually:

**Step 1: Create the config file**

Create `benchmark_configs.txt` in the `benchmark/solution/` directory (Harbor mounts this directory):

```bash
# In the benchmark/solution/ directory
echo "config_1 config_2 config_3" > benchmark/solution/benchmark_configs.txt
```

Or one config per line (comments allowed):
```bash
cat > benchmark/solution/benchmark_configs.txt << EOF
# Run these configs
config_1
config_2
config_3
EOF
```

**Step 2: Run Harbor**

```bash
harbor run -p benchmark -a <agent-name> -m <model>
```

Harbor mounts the `solution/` directory, so the solution script will automatically find and read `benchmark_configs.txt` from `/workspace/solution/benchmark_configs.txt`.

**Alternative: Environment variable (if supported)**

If your setup supports it, you can also try:
```bash
BENCHMARK_CONFIGS="config_1 config_2" harbor run -p benchmark -a <agent-name> -m <model>
```

**Default behavior**

If no configs are specified (no file and no env var), it defaults to `config_1`.

The `solution/solve.sh` script reads configs in this priority order:
1. `BENCHMARK_CONFIGS` environment variable (space-separated)
2. `/workspace/solution/benchmark_configs.txt` file (Harbor mounts solution/ directory here)
3. Command-line arguments (for direct execution)
4. Default: `config_1`

It runs `/benchmark_data/setup_and_run.sh` for each config sequentially.

**Execution Workflow:**
1. For each config:
   - Benchmark executes (agent processes event history and answers questions)
   - Execution time is tracked
   - LLM Judge evaluation runs immediately after completion
   - Results (metrics + execution time) are saved to MongoDB (if configured)
2. Process repeats for next config

**Note**: The current setup is optimized for claude-code which is pre-installed in the container. You may need to configure Harbor to use the container's claude-code installation.

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
- Python packages: openai, pyyaml, pydantic, python-dotenv, pymongo

## Evaluation and Results Storage

### LLM-as-Judge Evaluation

After each config execution, the system automatically:
1. Evaluates agent answers using an LLM judge
2. Calculates metrics: `total_questions`, `correct_count`, `accuracy`, `avg_score`, `avg_confidence`
3. Logs execution time for the config
4. Saves results to MongoDB (if configured)

### MongoDB Integration

Results are saved to MongoDB with the following structure (one record per config):

```json
{
  "experiment_name": "experiment_20250112_143022_config_1_config_2",
  "config_name": "config_1",
  "dataset_name": "event_history_1",
  "agent_name": "CodeAgent",
  "task_name": "config_1",
  "total_questions": 3,
  "correct_count": 2,
  "accuracy": 0.6667,
  "avg_score": 0.85,
  "avg_confidence": 0.92,
  "execution_time_seconds": 245.67,
  "timestamp": "2025-01-12T14:30:22.123Z",
  "created_at": "2025-01-12T14:30:22.123456"
}
```

**Experiment Name:**
- Automatically generated if not provided: `experiment_YYYYMMDD_HHMMSS_<config_summary>`
- Can be set via `EXPERIMENT_NAME` environment variable when running `run_benchmark.sh`
- All configs from the same run share the same experiment name, allowing you to group related benchmark runs
- Example: `EXPERIMENT_NAME=baseline_test_2025 ./run_benchmark.sh config_1 config_2`

**Configuration:**
Add to `benchmark/environment/secrets.env`:
```bash
DB_NAME=your_database_name
CONNECTION_STRING=mongodb://your_connection_string
```

### Running in Stub Mode (for fast debugging)

To use the stub mode, which generates logs from a pre-recorded agent output (`oracle.txt`) instead of running the full benchmark:

```bash
STUB_MODE=true ORACLE_FILE=./jobs/2026-01-12__11-08-06/benchmark__b9NqGZ2/agent/oracle.txt ./run_benchmark.sh config_1
```

- Set `STUB_MODE=true` environment variable
- Provide the `ORACLE_FILE` environment variable pointing to the raw agent output file from a previous run
- The `run_benchmark.sh` script will automatically copy `oracle.txt` to `benchmark/solution/oracle.txt` and create a `benchmark/solution/stub_mode.txt` flag file for the container
- The `setup_and_run.sh` script will then use `parse_oracle_stub.py` to generate the benchmark logs, allowing the LLM Judge evaluation to run quickly
- Execution time in stub mode reflects the time to parse the oracle file, not the actual benchmark execution

## Differences from Original Setup

The Harbor version:
- Uses Harbor's task structure instead of docker-compose
- Can be run with Harbor's agent system
- Maintains the same execution flow via `setup_and_run.sh`
- Test verification uses Harbor's standard test format

## Output Structure

After running benchmarks, you'll find:

```
/benchmark_logs/
├── config_1_20250112_143022/
│   ├── summary.txt              # Summary of the benchmark run
│   ├── processing.log            # Initial data processing log
│   ├── execution_time.txt        # Execution duration in seconds
│   ├── questions/
│   │   ├── question_1.log        # Agent's answer to question 1
│   │   ├── question_2.log        # Agent's answer to question 2
│   │   └── ...
│   └── llm_judge_results.json    # Evaluation results (if evaluation ran)
├── config_2_20250112_143045/
│   └── ...
```

## Next Steps

1. **View Results**: Check MongoDB for aggregated results across all configs
2. **Analyze Performance**: Use execution times and accuracy metrics to compare different agents/configurations
3. **Enhanced Tests**: Update `tests/test_outputs.py` with specific verification logic for your benchmarks
4. **Agent Configuration**: Configure Harbor to use claude-code if needed for non-interactive runs


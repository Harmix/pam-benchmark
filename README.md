# PAM Benchmark

A Harbor-based benchmark for evaluating LLM agents on memory and context management tasks using the PAM (Proactive AI Manager) framework.

## Overview

This benchmark evaluates an LLM agent's ability to:
1. Process event history data (Linear tickets and Slack messages) from JSON files
2. Organize the data according to the PAM Memory Agent Guide structure
3. Answer questions about the processed data based on the organized information

## Project Structure

```
pam-benchmark/
├── tasks/
│   └── memtrack/                  # Harbor task definition
│       ├── environment/
│       │   ├── Dockerfile         # Container environment
│       │   ├── docker-compose.yaml
│       │   ├── requirements.txt   # Python dependencies
│       │   ├── setup_and_run.sh   # Task execution script
│       │   └── ...                # PAM guide files
│       ├── solution/
│       │   ├── solve.sh           # Entry point script
│       │   └── llm_judge_eval.py  # LLM evaluation script
│       ├── tests/
│       │   └── test_outputs.py    # Verification tests
│       ├── instruction.md         # Task description
│       └── task.toml              # Harbor task config
├── datasets/
│   └── memtrack/                  # Dataset (separate from task)
│       ├── test_configs/          # YAML configuration files
│       ├── test_event_histories/  # JSON event history files
│       └── registry.json          # Dataset registry metadata
└── secrets.env                    # API keys (gitignored)
```

## Prerequisites

1. Install [Harbor framework](https://harborframework.com/docs)
2. Have Docker installed and running
3. Create `secrets.env` in the project root with:
   ```bash
   ANTHROPIC_API_KEY=your_anthropic_api_key
   OPENAI_API_KEY=your_openai_api_key
   # Optional: MongoDB for results storage
   DB_NAME=your_database_name
   CONNECTION_STRING=mongodb://your_connection_string
   ```

## Quick Start

### Running with Harbor

Run tasks using the Harbor command with environment variables:

```bash
# Run multiple configs
EXPERIMENT_NAME=my_experiment TASK_CONFIGS=config_1,config_2 harbor run \
  -d memtrack@1.0 \
  --registry-path datasets/memtrack/registry.json \
  --force-build

# Run a single config
EXPERIMENT_NAME=baseline_test TASK_CONFIGS=config_vg_15 harbor run \
  -d memtrack@1.0 \
  -a claude-code \
  -m anthropic/claude-sonnet-4-20250514 \
  --registry-path datasets/memtrack/registry.json

# Run with Daytona for cloud scaling
EXPERIMENT_NAME=cloud_run TASK_CONFIGS=config_1,config_2,config_3 harbor run \
  -d memtrack@1.0 \
  -a claude-code \
  -m anthropic/claude-sonnet-4-20250514 \
  --registry-path datasets/memtrack/registry.json \
  --env daytona \
  -n 8
```

### Environment Variables

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `EXPERIMENT_NAME` | Name for grouping results in MongoDB | (none) | `baseline_2025` |
| `TASK_CONFIGS` | Comma-separated list of config names | `config_1` | `config_1,config_2,config_vg_15` |
| `DEBUG` | Enable stub mode for faster development (skips agent execution) | `false` | `true` |

**DEBUG Mode**: When `DEBUG=true`, the task uses a stub instead of running the actual agent. This speeds up development iteration by skipping the time-consuming agent execution. Useful for testing the evaluation pipeline, logging, and other infrastructure.

```bash
# Fast development run with DEBUG mode
DEBUG=true EXPERIMENT_NAME=dev_test TASK_CONFIGS=config_1 harbor run \
  -d memtrack@1.0 \
  --registry-path datasets/memtrack/registry.json \
  --force-build
```

To add a new environment variable, you need to define it in the terminal execution command and add it to `services.main.environment` in `tasks/memtrack/environment/docker-compose.yaml`.

### Available Configs

List available configs:
```bash
ls datasets/memtrack/test_configs/
```

Common configs include:
- `config_1` through `config_5` - Basic test scenarios
- `config_vg_1` through `config_vg_32` - Extended validation scenarios

## Build Configuration

The Docker build uses `docker-compose.yaml` with the build context set to the **project root**. This allows direct access to:
- `datasets/memtrack/` - the dataset files
- `tasks/memtrack/environment/` - Dockerfile and environment files
- `secrets.env` - API keys and credentials (at project root)

No dataset copying is required since the build context includes the entire project.

### Manual Build with Docker Compose

```bash
# From the project root
CONTEXT_DIR=$(pwd)/tasks/memtrack/environment docker-compose -f tasks/memtrack/environment/docker-compose.yaml build
```

### Docker Compose Environment Variables

The `docker-compose.yaml` expects these environment variables:
- `CONTEXT_DIR` - Absolute path to task's environment/ directory
- `MAIN_IMAGE_NAME` - Name for the built image
- `EXPERIMENT_NAME` - Experiment name for result grouping
- `TASK_CONFIGS` - Comma-separated config names to run
- `CPUS` / `MEMORY` - Resource limits
- `NETWORK_MODE` - Docker network mode (defaults to "bridge")

## Task Execution Flow

1. **Initialization**: The agent receives a YAML config file and corresponding event history JSON
2. **Memory Structure Creation**: Run `init.py` to create the PAM folder structure
3. **Data Processing**: Process event history JSON and organize it into:
   - Daily digests (chronological view)
   - Linear objects (ticket history)
   - Slack threads (channel conversations)
4. **Question Answering**: Answer questions based on the organized data
5. **Evaluation**: LLM judge evaluates answers against expected responses

## Evaluation and Results

### LLM-as-Judge Evaluation

After each config execution, the system automatically:
1. Evaluates agent answers using an LLM judge
2. Calculates metrics: `total_questions`, `correct_count`, `accuracy`, `avg_score`, `avg_confidence`
3. Logs execution time for the config
4. Saves results to MongoDB (if configured)

### MongoDB Results Structure

Results are saved with the following structure:

```json
{
  "experiment_name": "my_experiment",
  "config_name": "config_1",
  "dataset_name": "event_history_1",
  "agent_name": "CodeAgent",
  "total_questions": 3,
  "correct_count": 2,
  "accuracy": 0.6667,
  "avg_score": 0.85,
  "avg_confidence": 0.92,
  "execution_time_seconds": 245.67,
  "timestamp": "2025-01-16T14:30:22.123Z"
}
```

## Output Structure

After running tasks, logs are available at `/task_logs/` inside the container:

```
/task_logs/
├── config_1_20250116_143022/
│   ├── summary.txt              # Summary of the task run
│   ├── processing.log           # Initial data processing log
│   ├── execution_time.txt       # Execution duration in seconds
│   ├── questions/
│   │   ├── question_1.log       # Agent's answer to question 1
│   │   ├── question_2.log       # Agent's answer to question 2
│   │   └── ...
│   └── llm_judge_results.json   # Evaluation results
└── config_2_20250116_143545/
    └── ...
```

## Interactive Environment

To start an interactive environment for debugging:

```bash
harbor tasks start-env -p tasks/memtrack -e docker -a -i
```

Once inside, you can run tasks manually:

```bash
/task_data/setup_and_run.sh /task_data/test_configs/config_1.yaml
```

## Container Environment

The Docker environment includes:
- Python 3.11 with system dependencies (curl, git, jq, build-essential, tree)
- yq for YAML parsing
- Node.js 20 and Claude Code v2.0.76
- Python packages: openai, pyyaml, pydantic, python-dotenv, pymongo

# MemTrack Dataset

This dataset contains the test configurations and event histories for the MemTrack benchmark, which evaluates memory agents on Linear and Slack event data.

## Structure

```
memtrack/
├── test_configs/          # YAML configuration files defining benchmark scenarios
├── test_event_histories/  # JSON files with Linear and Slack event data
└── registry.json          # Dataset registry metadata
```

## Usage

This dataset is used by the MemTrack Harbor task. The dataset is separate from the task definition, following Harbor's separation of datasets and tasks.

## Using with Harbor

To use this dataset with Harbor, you can reference it using a custom registry:

```bash
# Using local registry
harbor run -d "memtrack@1.0" -a <agent> -m <model> --registry-path "datasets/memtrack/registry.json"

# Or if the registry is hosted at a URL
harbor run -d "memtrack@1.0" -a <agent> -m <model> --registry-url "<url/to/registry.json>"
```

The dataset will be made available to the task at runtime.

## Contents

- **test_configs/**: Contains YAML files that define:
  - Agent configuration
  - Benchmark questions
  - Expected answers
  - Event history references

- **test_event_histories/**: Contains JSON files with chronological Linear tickets and Slack messages that serve as the context for the benchmark questions.

## Integration with Harbor

This dataset follows Harbor's dataset conventions and can be referenced by Harbor tasks. The dataset is copied into the Docker container during build at `/benchmark_data/test_configs/` and `/benchmark_data/test_event_histories/`.

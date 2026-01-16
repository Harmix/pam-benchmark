# Using MemTrack Dataset with Harbor

## Quick Start

The MemTrack dataset can be used with Harbor using a custom registry. Here are the different ways to use it:

### Method 1: Using Local Registry Path

From the project root directory:

```bash
harbor run -d "memtrack@1.0" -a oracle -m <model> --registry-path "datasets/memtrack/registry.json"
```

### Method 2: Using Absolute Path

```bash
harbor run -d "memtrack@1.0" -a oracle -m <model> --registry-path "/absolute/path/to/datasets/memtrack/registry.json"
```

### Method 3: Using Registry URL (if hosted)

If you host the registry.json file at a URL:

```bash
harbor run -d "memtrack@1.0" -a oracle -m <model> --registry-url "https://example.com/memtrack/registry.json"
```

## With Different Agents

### Using Claude Code

```bash
harbor run -d "memtrack@1.0" -a claude-code -m anthropic/claude-3-5-sonnet-20241022 --registry-path "datasets/memtrack/registry.json"
```

### Using Terminus

```bash
harbor run -d "memtrack@1.0" -a terminus-2 -m anthropic/claude-haiku-4-5 --registry-path "datasets/memtrack/registry.json"
```

## Running Multiple Instances

To run multiple instances in parallel:

```bash
harbor run -d "memtrack@1.0" -a oracle -m <model> --registry-path "datasets/memtrack/registry.json" -n 10
```

## Notes

- The dataset name is `memtrack` and the version is `1.0` (as defined in `registry.json`)
- The `--registry-path` flag points to the `registry.json` file in the dataset directory
- Harbor will use the registry to locate and load the dataset files (test_configs and test_event_histories)
- The dataset will be made available to the task at the paths specified in the registry

## Integration with PAM Benchmark Task

If you're using this dataset with the PAM Benchmark task (`benchmark/`), the dataset is automatically copied into the Docker image during build. You can also use Harbor's dataset mounting feature if your task is configured to accept datasets at runtime.

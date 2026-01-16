# Building the PAM Benchmark Task

## Prerequisites

Before building the Docker image, you need to prepare the dataset:

```bash
# From the benchmark/ directory
./prepare_build.sh
```

This script copies the dataset from `../datasets/memtrack/` into `benchmark/datasets/memtrack/` so it's available in the Docker build context.

## Building with Harbor

Harbor will automatically handle the build process when you run:

```bash
harbor run -p benchmark -a <agent> -m <model>
```

However, if you need to build manually or if Harbor doesn't automatically run `prepare_build.sh`, you should run it first.

## Why This Is Needed

Harbor's Docker build context is limited to the task directory (`benchmark/`). Since the dataset is stored separately in `datasets/memtrack/` at the project root, it needs to be copied into the task directory before building so Docker can access it.

## Alternative: Using Harbor Dataset Mounting

In the future, this could be improved by using Harbor's dataset mounting feature (if available) to mount the dataset at runtime instead of copying it during build.

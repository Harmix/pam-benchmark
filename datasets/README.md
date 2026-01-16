# Datasets

This directory contains datasets used by Harbor tasks, following Harbor's separation of datasets from tasks.

## Structure

```
datasets/
└── memtrack/               # MemTrack benchmark dataset
    ├── test_configs/       # YAML configuration files
    ├── test_event_histories/ # JSON event history files
    ├── registry.json       # Dataset registry metadata
    └── README.md          # Dataset documentation
```

## Usage

Datasets are separate from tasks and can be referenced by multiple tasks. When building a Docker image for a task, the dataset needs to be available in the build context.

For the MemTrack benchmark task, the dataset is copied into the task directory during the build process using `benchmark/prepare_build.sh`.

## Adding New Datasets

To add a new dataset:

1. Create a new directory under `datasets/`
2. Add a `registry.json` file with dataset metadata
3. Add a `README.md` documenting the dataset
4. Update the task's build process to include the dataset if needed

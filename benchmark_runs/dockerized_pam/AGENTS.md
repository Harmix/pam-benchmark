# Repository Guidelines

## Project Structure & Module Organization
- Root houses `docker-compose.yml`, `Dockerfile`, and helper launch scripts (`setup_and_run.sh`, `run_all_isolated.sh`, `run_range_isolated.sh`) that orchestrate benchmarks.
- Benchmark adapters live in `mcp-servers/`; adjust `slack_wrapper.sh` and `linear_wrapper.sh` when wiring new MCP integrations.
- Scenario inputs reside in `test_configs/` (YAML configs) and `test_event_histories/` (JSON transcripts); fresh outputs and logs are written to `outputs*/` and `logs/`.
- Python utilities such as `data_loader.py`, `slack_mcp_server.py`, and `linear_mcp_server.py` live at the root; place new modules alongside their closest peers.

## Build, Test, and Development Commands
- `docker-compose up -d`: build the claude-code container and start it in detached mode.
- `docker-compose exec claude-code bash`: open an interactive shell inside the running container for iterative work.
- `docker-compose exec claude-code /workspace/setup_and_run.sh /workspace/test_configs/config_1.yaml`: execute the default benchmark pipeline; override the final argument for other configs.
- `./run_all_isolated.sh` (host): iterate through every configuration with clean containers. Run `./run_range_isolated.sh 1 10` for a targeted slice.

## Coding Style & Naming Conventions
- Python scripts target CPython 3; keep to PEP 8, 4-space indentation, and prefer descriptive snake_case for modules, functions, and file names.
- When extending benchmark helpers, mirror existing function names and surface new environment variables through upper-case constants.
- Bash scripts should remain POSIX-compatible where possible; include defensive guards (`set -euo pipefail`) on new entrypoints and document expected parameters in comments.

## Testing Guidelines
- Treat benchmark runs as the regression suite: run `setup_and_run.sh` inside the container against a relevant `test_configs/*.yaml`.
- Confirm Slack and Linear MCP smoke tests pass; failures usually indicate missing credentials or schema drift.
- Inspect generated `logs/<config>_*/questions/question_N.log` and `summary.txt` for anomalies before publishing results, and redact sensitive responses.

## Commit & Pull Request Guidelines
- The distributed bundle lacks Git history; use Conventional Commit prefixes (e.g., `feat:`, `fix:`, `docs:`) so downstream mirrors can auto-changelog.
- Scope commits narrowly: pair script updates with the config or documentation that consumes them, and note impacted configs in the body.
- Pull requests should link the benchmark ticket, list exercised commands, attach representative log excerpts, and flag any configs intentionally skipped.

## Security & Configuration Tips
- Never commit `.env` or credentialed YAML; the runtime expects `ANTHROPIC_API_KEY` to be injected at deploy time.
- Scrub output artifacts before sharing externally—`outputs/` can capture raw MCP replies that may include workspace metadata or tokens.
- Archive per-run log directories after review to keep workspaces lean and auditable.

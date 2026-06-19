"""Generate an HTML or Markdown report from MongoDB results for one experiment.

Usage:
    uv run python scripts/generate_report.py --exp-name <name> [--dataset locomo] [--format html|md]
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import typer  # noqa: E402
from rich.console import Console  # noqa: E402

from env import load_secrets  # noqa: E402
from reporting.html import render_to_file  # noqa: E402
from reporting.markdown import render_markdown  # noqa: E402
from reporting.query import fetch_experiment  # noqa: E402

app = typer.Typer(add_completion=False, no_args_is_help=True)
console = Console()


@app.command()
def main(
    exp_name: str = typer.Option(..., "--exp-name", help="Experiment identifier"),
    dataset: str = typer.Option("locomo", "--dataset", help="Dataset name"),
    output_dir: str = typer.Option(None, "--output-dir", help="Defaults to reports/<exp-name>"),
    fmt: str = typer.Option("html", "--format", help="html | md"),
    mcp: bool = typer.Option(
        False, "--mcp", help="Read the MCP-on-harness collection (<dataset>_mcp_results)"
    ),
    collection: str = typer.Option(
        None, "--collection", help="Override the Mongo collection (default <dataset>_results)"
    ),
) -> None:
    """Pull Mongo rows for `--exp-name` and render the report."""
    load_secrets()

    out = Path(output_dir) if output_dir else Path("reports") / exp_name
    out.mkdir(parents=True, exist_ok=True)

    coll = collection or (f"{dataset}_mcp_results" if mcp else None)
    docs = fetch_experiment(exp_name=exp_name, dataset=dataset, collection=coll)
    if not docs:
        console.print(
            f"[red]No documents found[/red] for exp_name={exp_name!r} in "
            f"collection {coll or f'{dataset}_results'}."
        )
        raise typer.Exit(code=1)

    if fmt == "html":
        path = out / "report.html"
        render_to_file(dataset=dataset, exp_name=exp_name, docs=docs, output_path=path)
        console.print(f"[green]✓[/green] HTML report → [cyan]{path}[/cyan]")
    elif fmt == "md":
        path = out / "report.md"
        path.write_text(
            render_markdown(dataset=dataset, exp_name=exp_name, docs=docs),
            encoding="utf-8",
        )
        console.print(f"[green]✓[/green] Markdown report → [cyan]{path}[/cyan]")
    else:
        console.print(f"[red]Unknown --format:[/red] {fmt} (use html or md)")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()

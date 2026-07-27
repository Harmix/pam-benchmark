"""Verify (or download) dataset files for a given dataset name.

Usage:
    uv run python scripts/download_data.py --dataset locomo

M1 only supports LoCoMo; the file is shipped with the repo, so this script
currently verifies the file exists. When upstream licenses allow, replace
the verifier with a real downloader (e.g. via `requests` + sha256 checksum).
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make `src/` importable regardless of how the script is invoked.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

import typer  # noqa: E402
from rich.console import Console  # noqa: E402

app = typer.Typer(add_completion=False, no_args_is_help=True)
console = Console()


@app.command()
def main(
    dataset: str = typer.Option(..., "--dataset", help="Dataset name (e.g. locomo)"),
    force: bool = typer.Option(False, "--force", help="Re-download even if present"),
) -> None:
    """Verify or download the requested dataset."""
    if dataset == "locomo":
        from datasets.locomo.loader import DEFAULT_DATA_PATH

        if DEFAULT_DATA_PATH.exists() and not force:
            size_mb = DEFAULT_DATA_PATH.stat().st_size / 1024 / 1024
            console.print(
                f"[green]✓[/green] LoCoMo data present at "
                f"[cyan]{DEFAULT_DATA_PATH}[/cyan] ({size_mb:.2f} MB)"
            )
            return
        console.print(
            "[yellow]LoCoMo download not implemented yet.[/yellow] "
            "Obtain `locomo10.json` from https://github.com/snap-research/locomo "
            f"and place it at [cyan]{DEFAULT_DATA_PATH}[/cyan]."
        )
        raise typer.Exit(code=1)

    if dataset == "harmix":
        # The bench-cases JSON and the per-environment memory snapshots both live
        # in GCS and are read at run time — nothing is bundled locally. Verify the
        # bench-cases object is reachable so misconfigured auth fails loudly here.
        from datasets.harmix.loader import DEFAULT_DATA_URI, HarmixLoader

        try:
            ld = HarmixLoader()
        except Exception as exc:  # surface any GCS/auth failure as a clear error
            console.print(
                f"[red]Could not read Harmix bench cases from[/red] [cyan]{DEFAULT_DATA_URI}[/cyan]: {exc}"
            )
            raise typer.Exit(code=1) from exc

        console.print(
            f"[green]✓[/green] Harmix bench cases reachable at "
            f"[cyan]{DEFAULT_DATA_URI}[/cyan] ({ld.num_samples()} environments)"
        )
        return

    console.print(f"[red]Unknown dataset:[/red] {dataset}")
    console.print("Supported: locomo, harmix")
    raise typer.Exit(code=1)


if __name__ == "__main__":
    app()

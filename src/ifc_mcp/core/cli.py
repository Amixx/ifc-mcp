"""CLI commands owned by the core module."""

from __future__ import annotations

import json
from pathlib import Path

import click

from ifc_mcp.core.pipeline import load_model_artifacts
from ifc_mcp.core.progress import CliProgressReporter


@click.command("info")
@click.argument("file_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--quiet", is_flag=True, help="Suppress progress output.")
@click.option("--verbose", is_flag=True, help="Show detailed progress, timing, and memory stats.")
@click.option("--no-geometry", is_flag=True, help="Skip geometry extraction for faster loading.")
def info_command(file_path: Path, quiet: bool, verbose: bool, no_geometry: bool) -> None:
    """Print quick model summary as JSON."""
    if quiet and verbose:
        raise click.UsageError("Cannot use --quiet and --verbose together.")
    reporter = CliProgressReporter(enabled=not quiet, verbose=verbose)
    reporter.begin(str(file_path), label="info")
    _, _, index = load_model_artifacts(str(file_path), progress_callback=reporter.event if reporter.enabled else None, extract_geometry=not no_geometry)
    reporter.done(label="info")
    click.echo(json.dumps(index.get_summary(), indent=2))

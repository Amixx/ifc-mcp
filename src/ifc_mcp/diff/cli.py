"""CLI commands owned by the diff module."""

from __future__ import annotations

import json
from pathlib import Path

import click

from ifc_mcp.core.progress import CliProgressReporter
from ifc_mcp.diff.engine import diff_ifc_files


@click.command("diff")
@click.argument("old_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("new_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text", show_default=True)
@click.option("--quiet", is_flag=True, help="Suppress progress output.")
@click.option("--verbose", is_flag=True, help="Show detailed progress, timing, and memory stats.")
def diff_command(old_file: Path, new_file: Path, output_format: str, quiet: bool, verbose: bool) -> None:
    """Diff two IFC models (lightweight deterministic wrapper)."""
    if quiet and verbose:
        raise click.UsageError("Cannot use --quiet and --verbose together.")
    reporter = CliProgressReporter(enabled=not quiet, verbose=verbose)
    reporter.begin(str(old_file), label="diff(old)")
    reporter.begin(str(new_file), label="diff(new)")
    diff_result = diff_ifc_files(
        str(old_file),
        str(new_file),
        progress_callback=reporter.event if reporter.enabled else None,
    )
    reporter.done(label="diff")

    if output_format == "json":
        click.echo(json.dumps(diff_result, indent=2))
        return

    click.echo(f"Added: {diff_result['summary']['added']}")
    click.echo(f"Removed: {diff_result['summary']['removed']}")
    click.echo(f"Changed: {diff_result['summary']['changed']}")

"""CLI commands owned by the diff module."""

from __future__ import annotations

import json
from pathlib import Path

import click

from ifc_mcp.diff.engine import diff_ifc_files


@click.command("diff")
@click.argument("old_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("new_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text", show_default=True)
def diff_command(old_file: Path, new_file: Path, output_format: str) -> None:
    """Diff two IFC models (lightweight deterministic wrapper)."""
    diff_result = diff_ifc_files(str(old_file), str(new_file))

    if output_format == "json":
        click.echo(json.dumps(diff_result, indent=2))
        return

    click.echo(f"Added: {diff_result['summary']['added']}")
    click.echo(f"Removed: {diff_result['summary']['removed']}")
    click.echo(f"Changed: {diff_result['summary']['changed']}")

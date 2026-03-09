"""CLI commands owned by the lint module."""

from __future__ import annotations

import json
from pathlib import Path

import click

from ifc_mcp.lint.engine import lint_ifc_model


@click.command("lint")
@click.argument("file_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--config", "config_path", type=click.Path(exists=True, dir_okay=False, path_type=Path), default=None)
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text", show_default=True)
def lint_command(file_path: Path, config_path: Path | None, output_format: str) -> None:
    """Run lint checks for an IFC model."""
    result = lint_ifc_model(str(file_path), str(config_path) if config_path else None)

    if output_format == "json":
        click.echo(json.dumps(result, indent=2))
    else:
        summary = result["summary"]
        click.echo(
            f"Lint summary: {summary['total']} findings "
            f"({summary['errors']} errors, {summary['warnings']} warnings, {summary['info']} info)"
        )
        for finding in result["results"]:
            gid = finding["global_id"] or "-"
            click.echo(
                f"[{finding['severity'].upper()}] {finding['rule_id']} {gid}: {finding['message']}"
            )

    if result["summary"]["errors"] > 0:
        raise SystemExit(1)

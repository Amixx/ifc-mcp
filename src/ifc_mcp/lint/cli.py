"""CLI commands owned by the lint module."""

from __future__ import annotations

import json
from pathlib import Path

import click

from ifc_mcp.core.progress import CliProgressReporter
from ifc_mcp.lint.engine import lint_ifc_model


@click.command("lint")
@click.argument("file_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--config", "config_path", type=click.Path(exists=True, dir_okay=False, path_type=Path), default=None)
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text", show_default=True)
@click.option("--quiet", is_flag=True, help="Suppress progress output.")
@click.option("--verbose", is_flag=True, help="Show detailed progress, timing, and memory stats.")
def lint_command(
    file_path: Path,
    config_path: Path | None,
    output_format: str,
    quiet: bool,
    verbose: bool,
) -> None:
    """Run lint checks for an IFC model."""
    if quiet and verbose:
        raise click.UsageError("Cannot use --quiet and --verbose together.")
    reporter = CliProgressReporter(enabled=not quiet, verbose=verbose)
    reporter.begin(str(file_path), label="lint")
    result = lint_ifc_model(
        str(file_path),
        str(config_path) if config_path else None,
        progress_callback=reporter.event if reporter.enabled else None,
    )
    reporter.done(label="lint")

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

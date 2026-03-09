"""CLI commands owned by the MCP module."""

from __future__ import annotations

from pathlib import Path

import click

from ifc_mcp.core.progress import CliProgressReporter
from ifc_mcp.mcp.server import run_server


@click.command("serve")
@click.argument("file_path", required=False, type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--transport", type=click.Choice(["stdio", "http"]), default="stdio", show_default=True)
@click.option("--port", type=int, default=8000, show_default=True)
@click.option("--quiet", is_flag=True, help="Suppress progress output.")
@click.option("--verbose", is_flag=True, help="Show detailed progress, timing, and memory stats.")
@click.option("--with-geometry", is_flag=True, help="Enable eager geometry extraction for loaded models (slower).")
def serve_command(
    file_path: Path | None,
    transport: str,
    port: int,
    quiet: bool,
    verbose: bool,
    with_geometry: bool,
) -> None:
    """Run ifc-mcp server (optionally preloading one IFC model file)."""
    if quiet and verbose:
        raise click.UsageError("Cannot use --quiet and --verbose together.")
    reporter = CliProgressReporter(enabled=not quiet, verbose=verbose)
    if file_path:
        reporter.begin(str(file_path), label="serve-preload")
    run_server(
        str(file_path) if file_path else None,
        transport=transport,
        port=port,
        progress_callback=reporter.event if reporter.enabled else None,
        with_geometry=with_geometry,
    )

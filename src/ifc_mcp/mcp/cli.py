"""CLI commands owned by the MCP module."""

from __future__ import annotations

from pathlib import Path

import click

from ifc_mcp.mcp.server import run_server


@click.command("serve")
@click.argument("file_path", required=False, type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--transport", type=click.Choice(["stdio", "http"]), default="stdio", show_default=True)
@click.option("--port", type=int, default=8000, show_default=True)
def serve_command(file_path: Path | None, transport: str, port: int) -> None:
    """Run ifc-mcp server (optionally preloading one IFC model file)."""
    run_server(str(file_path) if file_path else None, transport=transport, port=port)

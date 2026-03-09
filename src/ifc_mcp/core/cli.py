"""CLI commands owned by the core module."""

from __future__ import annotations

import json
from pathlib import Path

import click

from ifc_mcp.core.index import build_index
from ifc_mcp.core.parser import parse_ifc
from ifc_mcp.core.scene import build_scene_model


@click.command("info")
@click.argument("file_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
def info_command(file_path: Path) -> None:
    """Print quick model summary as JSON."""
    parsed = parse_ifc(str(file_path))
    scene = build_scene_model(parsed)
    index = build_index(parsed, scene)
    click.echo(json.dumps(index.get_summary(), indent=2))

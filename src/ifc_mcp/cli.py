"""Top-level CLI that composes module-owned subcommands."""

from __future__ import annotations

import sys

import click

from ifc_mcp import __version__
from ifc_mcp.core.cli import info_command
from ifc_mcp.diff.cli import diff_command
from ifc_mcp.lint.cli import lint_command
from ifc_mcp.mcp.cli import serve_command


@click.group()
@click.version_option(version=__version__, prog_name="ifc-mcp")
def main() -> None:
    """ifc-mcp CLI."""


main.add_command(serve_command)
main.add_command(lint_command)
main.add_command(diff_command)
main.add_command(info_command)


if __name__ == "__main__":  # pragma: no cover
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)

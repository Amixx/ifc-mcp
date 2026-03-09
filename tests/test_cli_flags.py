"""CLI flag surface tests for geometry mode options."""

from __future__ import annotations

from click.testing import CliRunner

from ifc_mcp.cli import main


def test_info_uses_with_geometry_flag():
    runner = CliRunner()
    result = runner.invoke(main, ["info", "--help"])
    assert result.exit_code == 0
    assert "--with-geometry" in result.output
    assert "--no-geometry" not in result.output


def test_lint_uses_with_geometry_flag():
    runner = CliRunner()
    result = runner.invoke(main, ["lint", "--help"])
    assert result.exit_code == 0
    assert "--with-geometry" in result.output


def test_serve_uses_with_geometry_flag():
    runner = CliRunner()
    result = runner.invoke(main, ["serve", "--help"])
    assert result.exit_code == 0
    assert "--with-geometry" in result.output

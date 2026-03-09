"""Tests for quantity tools."""

from __future__ import annotations

from ifc_mcp.tools import quantities


def test_get_quantities(model_index):
    result = quantities.get_quantities(model_index)
    assert result["count"] >= 0
    assert "total_area" in result


def test_get_material_summary(model_index):
    result = quantities.get_material_summary(model_index)
    assert "materials" in result


def test_get_space_summary(model_index):
    result = quantities.get_space_summary(model_index)
    assert "spaces" in result

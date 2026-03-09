"""Tests for spatial tools."""

from __future__ import annotations

from ifc_mcp.tools import spatial


def test_get_spatial_structure(model_index):
    result = spatial.get_spatial_structure(model_index)
    assert "roots" in result


def test_get_elements_in_space(model_index):
    spaces = model_index.by_type.get("IfcSpace", [])
    if not spaces:
        result = spatial.get_elements_in_space(model_index, "missing")
        assert "error" in result
        return

    result = spatial.get_elements_in_space(model_index, spaces[0].global_id)
    assert "results" in result
    assert isinstance(result["results"], list)

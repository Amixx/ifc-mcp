"""Tests for meta tools."""

from __future__ import annotations

from ifc_mcp.tools import meta


def test_get_model_summary(model_index):
    result = meta.get_model_summary(model_index)
    assert "metadata" in result
    assert "counts_by_ifc_class" in result


def test_list_property_sets(model_index):
    result = meta.list_property_sets(model_index)
    assert "property_sets" in result


def test_get_element_geometry_bounds(model_index):
    guid = next(iter(model_index.by_guid))
    result = meta.get_element_geometry_bounds(model_index, guid)
    assert "bounds" in result or "error" in result

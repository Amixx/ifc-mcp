"""Tests for query tools."""

from __future__ import annotations

from ifc_mcp.tools import query


def test_get_element_by_id(model_index):
    guid = next(iter(model_index.by_guid))
    result = query.get_element_by_id(model_index, guid)
    assert result["global_id"] == guid


def test_search_elements_by_class(model_index):
    result = query.search_elements(model_index, ifc_class="IfcWall")
    assert "count" in result
    assert isinstance(result["results"], list)


def test_get_element_properties(model_index):
    guid = next(iter(model_index.by_guid))
    result = query.get_element_properties(model_index, guid)
    assert isinstance(result, dict)

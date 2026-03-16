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


def test_audit_property_coverage(model_index):
    result = query.audit_property_coverage(model_index, property_names=["IsExternal"], ifc_class="IfcWall")
    assert "total" in result
    assert "properties" in result
    assert result["properties"][0]["property_name"] == "IsExternal"


def test_audit_property_coverage_with_aliases(model_index):
    result = query.audit_property_coverage(
        model_index,
        requirements=[{"name": "External", "aliases": ["IsExternal"]}],
        ifc_class="IfcWall",
    )
    assert result["properties"][0]["property_name"] == "External"
    assert result["properties"][0]["aliases"] == ["IsExternal"]


def test_get_element_properties(model_index):
    guid = next(iter(model_index.by_guid))
    result = query.get_element_properties(model_index, guid)
    assert isinstance(result, dict)

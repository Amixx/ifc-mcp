"""Tests for analysis tools."""

from __future__ import annotations

from ifc_mcp.tools import analysis


def test_find_elements_by_property(model_index):
    result = analysis.find_elements_by_property(model_index, property_name="IsExternal", operator="exists")
    assert "results" in result


def test_get_classification(model_index):
    guid = next(iter(model_index.by_guid))
    result = analysis.get_classification(model_index, guid)
    assert "classifications" in result or "error" in result


def test_get_type_info(model_index):
    typed_entity = next((e for e in model_index.by_guid.values() if e.type_guid), None)
    if typed_entity is None:
        return
    result = analysis.get_type_info(model_index, typed_entity.global_id)
    assert "type" in result
    assert "instances" in result

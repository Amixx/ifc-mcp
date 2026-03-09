"""Tests for relationship tools."""

from __future__ import annotations

from ifc_mcp.tools import relationships


def test_get_connected_elements(model_index):
    guid = next(iter(model_index.by_guid))
    result = relationships.get_connected_elements(model_index, guid)
    assert "connections" in result


def test_get_contained_elements(model_index):
    relations = model_index.relationships.get("spatial_containment", [])
    if not relations:
        return
    container_guid = relations[0]["container_guid"]
    result = relationships.get_contained_elements(model_index, container_guid)
    assert "children" in result


def test_get_element_material(model_index):
    with_material = next((e for e in model_index.by_guid.values() if e.materials), None)
    if with_material is None:
        return
    result = relationships.get_element_material(model_index, with_material.global_id)
    assert "materials" in result

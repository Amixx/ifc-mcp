"""Tests for quantity tools."""

from __future__ import annotations

from types import SimpleNamespace

from ifc_mcp.tools import quantities


def test_get_quantities(model_index):
    result = quantities.get_quantities(model_index)
    assert result["count"] >= 0
    assert "total_area" in result


def test_get_material_summary(model_index):
    result = quantities.get_material_summary(model_index)
    assert "materials" in result


def test_get_material_summary_reports_non_overlapping_coverage():
    index = SimpleNamespace(
        by_guid={
            "WALL1": SimpleNamespace(
                ifc_class="IfcWall",
                property_sets={},
                geometry_bounds=None,
                materials=[
                    SimpleNamespace(name="Concrete"),
                    SimpleNamespace(name="Insulation"),
                ],
            ),
            "DOOR1": SimpleNamespace(
                ifc_class="IfcDoor",
                property_sets={},
                geometry_bounds=None,
                materials=[],
            ),
        }
    )

    result = quantities.get_material_summary(index)
    assert result["covered_element_count"] == 1
    assert result["total_element_count"] == len(index.by_guid)
    assert result["coverage"] == 0.5
    assert sum(row["element_count"] for row in result["materials"]) == 2


def test_get_space_summary(model_index):
    result = quantities.get_space_summary(model_index)
    assert "spaces" in result

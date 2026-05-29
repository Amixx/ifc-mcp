"""Tests for targeted geometry bounds helpers."""

from __future__ import annotations

import ifcopenshell

from ifc_mcp.core.geometry import extract_element_bounds_batch


def test_batch_bounds_uses_parametric_swept_solid_before_tessellation() -> None:
    ifc = ifcopenshell.open("data/BasicHouse.ifc")
    element = ifc.by_guid("2DedXznHnDaeAWsrTB_qBp")

    result = extract_element_bounds_batch(ifc, include_guids={element.GlobalId}, threads=1)

    assert result.diagnostics == []
    assert len(result.bounds) == 1
    row = result.bounds[0]
    assert row["global_id"] == element.GlobalId
    assert row["ifc_class"] == "IfcWallStandardCase"
    assert row["tag"] == "1298028"
    assert row["min_x_m"] == -7.591
    assert row["max_x_m"] == 15.009
    assert row["min_y_m"] == 4.202
    assert row["max_y_m"] == 4.742
    assert row["min_z_m"] == 0.0
    assert row["max_z_m"] == 2.535
    assert row["source"] == "ifc parametric swept solid"


def test_batch_bounds_falls_back_to_iterator_for_mesh_representation() -> None:
    ifc = ifcopenshell.open("data/Building-Architecture.ifc")
    element = next(
        element
        for element in ifc.by_type("IfcElement")
        if getattr(element, "Representation", None) is not None
    )

    result = extract_element_bounds_batch(ifc, include_guids={element.GlobalId}, threads=1)

    assert result.diagnostics == []
    assert len(result.bounds) == 1
    assert result.bounds[0]["global_id"] == element.GlobalId
    assert result.bounds[0]["source"] == "ifcopenshell.geom world coordinates"
    assert result.bounds[0]["vertex_count"] > 0

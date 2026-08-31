"""Tests for targeted geometry bounds helpers."""

from __future__ import annotations

import ifcopenshell

from ifc_mcp.core.geometry import extract_element_bounds_batch, extract_element_meshes_batch


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


def test_mesh_batch_produces_one_geometry_and_one_instance_for_a_single_element() -> None:
    ifc = ifcopenshell.open("data/Building-Architecture.ifc")
    element = next(
        element
        for element in ifc.by_type("IfcElement")
        if getattr(element, "Representation", None) is not None
    )

    result = extract_element_meshes_batch(ifc, include_guids={element.GlobalId}, threads=1)

    assert result.diagnostics == []
    assert len(result.instances) == 1
    instance = result.instances[0]
    assert instance["global_id"] == element.GlobalId
    assert instance["ifc_class"] == element.is_a()
    assert len(instance["matrix"]) == 16
    assert instance["geometry_id"] in result.geometries
    geometry = result.geometries[instance["geometry_id"]]
    assert len(geometry["positions"]) > 0
    assert len(geometry["positions"]) % 3 == 0
    assert len(geometry["indices"]) > 0
    assert len(geometry["indices"]) % 3 == 0


def test_mesh_batch_dedupes_identical_representations_into_one_geometry() -> None:
    ifc = ifcopenshell.open("data/Building-Architecture.ifc")
    elements = [e for e in ifc.by_type("IfcElement") if getattr(e, "Representation", None)]

    result = extract_element_meshes_batch(ifc, threads=4)

    assert len(result.instances) <= len(elements)
    assert len(result.instances) > 0
    # Every production BIM-viewer format (SVF2/XKT/Speckle) leans on instance dedup for
    # repeated element types; geometry.id reuse must never produce *more* geometries than
    # instances even when this small fixture has no actually-repeated element types.
    assert len(result.geometries) <= len(result.instances)


def test_mesh_batch_time_budget_cuts_off_iterator_and_reports_diagnostics() -> None:
    ifc = ifcopenshell.open("data/Building-Architecture.ifc")

    result = extract_element_meshes_batch(ifc, threads=1, time_budget_s=0.0)

    assert result.diagnostics
    assert any("time budget" in row["reason"] for row in result.diagnostics)


def _triangle_count(result) -> int:
    return sum(len(geometry["indices"]) // 3 for geometry in result.geometries.values())


def test_mesh_batch_deflection_defaults_leave_ifcopenshell_settings_untouched() -> None:
    ifc = ifcopenshell.open("data/Building-Architecture.ifc")

    default = extract_element_meshes_batch(ifc, threads=1)
    explicit = extract_element_meshes_batch(
        ifc, threads=1, linear_deflection=0.001, angular_deflection=0.5
    )

    assert _triangle_count(default) == _triangle_count(explicit)


def test_mesh_batch_coarse_deflection_reduces_triangles_without_dropping_elements() -> None:
    ifc = ifcopenshell.open("data/BasicHouse.ifc")

    fine = extract_element_meshes_batch(ifc, threads=1, linear_deflection=0.001)
    coarse = extract_element_meshes_batch(
        ifc, threads=1, linear_deflection=0.2, angular_deflection=1.2
    )

    assert _triangle_count(coarse) < _triangle_count(fine)
    assert {row["global_id"] for row in coarse.instances} == {
        row["global_id"] for row in fine.instances
    }


def test_mesh_batch_exclude_openings_drops_opening_products_and_boolean_cuts() -> None:
    ifc = ifcopenshell.open("data/BasicHouse.ifc")
    voided_wall = next(
        rel.RelatingBuildingElement
        for rel in ifc.by_type("IfcRelVoidsElement")
        if rel.RelatingBuildingElement.is_a("IfcWall")
    )
    guids = {voided_wall.GlobalId} | {
        opening.GlobalId for opening in ifc.by_type("IfcOpeningElement")
    }

    cut = extract_element_meshes_batch(ifc, threads=1, include_guids=guids)
    uncut = extract_element_meshes_batch(
        ifc, threads=1, include_guids=guids, exclude_openings=True
    )

    assert any(row["ifc_class"] == "IfcOpeningElement" for row in cut.instances)
    assert {row["global_id"] for row in uncut.instances} == {voided_wall.GlobalId}
    assert all(
        row["ifc_class"] != "IfcOpeningElement" for row in uncut.diagnostics
    )

    def wall_triangles(result) -> int:
        row = next(r for r in result.instances if r["global_id"] == voided_wall.GlobalId)
        return len(result.geometries[row["geometry_id"]]["indices"]) // 3

    assert wall_triangles(uncut) < wall_triangles(cut)


def _guids_with_global_id(ifc) -> set[str]:
    return {
        element.GlobalId
        for element in ifc.by_type("IfcElement")
        if getattr(element, "GlobalId", None)
    }


def test_bounds_batch_default_scans_every_element_and_partitions_them() -> None:
    ifc = ifcopenshell.open("data/Building-Architecture.ifc")

    result = extract_element_bounds_batch(ifc, threads=1)

    assert result.complete
    assert result.unscanned == []
    bounded = {row["global_id"] for row in result.bounds}
    unbounded = {row["global_id"] for row in result.diagnostics}
    assert bounded.isdisjoint(unbounded)
    assert bounded | unbounded == _guids_with_global_id(ifc)


def test_bounds_batch_without_a_budget_never_blames_a_time_budget() -> None:
    ifc = ifcopenshell.open("data/Building-Architecture.ifc")

    result = extract_element_bounds_batch(ifc, threads=1)

    assert all("time budget" not in row["reason"] for row in result.diagnostics)


def test_bounds_batch_default_is_deterministic_across_runs() -> None:
    ifc = ifcopenshell.open("data/Building-Architecture.ifc")

    first = extract_element_bounds_batch(ifc, threads=1)
    second = extract_element_bounds_batch(ifc, threads=1)

    assert first.bounds == second.bounds
    assert first.diagnostics == second.diagnostics


def test_bounds_batch_time_budget_reports_unscanned_apart_from_diagnostics() -> None:
    ifc = ifcopenshell.open("data/Building-Architecture.ifc")

    result = extract_element_bounds_batch(ifc, threads=1, time_budget_s=0.0)

    assert not result.complete
    assert result.unscanned
    expired = "geometry iterator time budget exceeded"
    assert all(row["reason"] == expired for row in result.unscanned)
    unscanned = {row["global_id"] for row in result.unscanned}
    assert unscanned.isdisjoint({row["global_id"] for row in result.diagnostics})
    assert unscanned.isdisjoint({row["global_id"] for row in result.bounds})
    assert all("time budget" not in row["reason"] for row in result.diagnostics)


def test_bounds_batch_time_budget_only_moves_elements_out_of_the_complete_scan() -> None:
    """A truncated run is a prefix: it never bounds an element the complete run could not."""
    ifc = ifcopenshell.open("data/Building-Architecture.ifc")

    complete = extract_element_bounds_batch(ifc, threads=1)
    truncated = extract_element_bounds_batch(ifc, threads=1, time_budget_s=0.0)

    assert {row["global_id"] for row in truncated.bounds} <= {
        row["global_id"] for row in complete.bounds
    }
    assert {row["global_id"] for row in truncated.unscanned} <= {
        row["global_id"] for row in complete.bounds
    } | {row["global_id"] for row in complete.diagnostics}

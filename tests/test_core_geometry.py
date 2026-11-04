"""Tests for targeted geometry bounds helpers."""

from __future__ import annotations

from typing import Any

import ifcopenshell
import ifcopenshell.api.context
import ifcopenshell.api.project
import ifcopenshell.api.root
import ifcopenshell.api.unit
import pytest

from ifc_mcp.core.geometry import (
    extract_element_bounds_batch,
    extract_element_meshes_batch,
)


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
    uncut = extract_element_meshes_batch(ifc, threads=1, include_guids=guids, exclude_openings=True)

    assert any(row["ifc_class"] == "IfcOpeningElement" for row in cut.instances)
    assert {row["global_id"] for row in uncut.instances} == {voided_wall.GlobalId}
    assert all(row["ifc_class"] != "IfcOpeningElement" for row in uncut.diagnostics)

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


@pytest.mark.parametrize(
    "mapping_target",
    [
        pytest.param({"origin": (5000.0, 0.0, 0.0)}, id="offset-mapping-origin"),
        pytest.param({"axis1": (2.0, 0.0, 0.0)}, id="unnormalised-axis"),
        pytest.param({"scale2": 2.0, "scale3": 3.0}, id="non-uniform-scale"),
    ],
)
def test_batch_bounds_reads_a_mapped_item_where_tessellation_puts_it(
    mapping_target: dict[str, Any],
) -> None:
    ifc, wall = _wall_with_mapped_box(**mapping_target)

    parametric = extract_element_bounds_batch(ifc, threads=1, prefer_parametric=True)
    tessellated = extract_element_bounds_batch(ifc, threads=1, prefer_parametric=False)

    [parametric_row] = parametric.bounds
    [tessellated_row] = tessellated.bounds
    assert parametric_row["source"] == "ifc parametric swept solid"
    assert _extent(parametric_row) == _extent(tessellated_row)
    assert parametric_row["global_id"] == wall.GlobalId


def test_batch_bounds_leaves_a_mapped_item_with_a_2d_target_to_tessellation() -> None:
    ifc, wall = _wall_with_mapped_box()
    [item] = wall.Representation.Representations[0].Items
    item.MappingTarget = ifc.createIfcCartesianTransformationOperator2D(
        None, None, ifc.createIfcCartesianPoint((0.0, 0.0)), None
    )

    [row] = extract_element_bounds_batch(ifc, threads=1, prefer_parametric=True).bounds

    assert row["source"] == "ifcopenshell.geom world coordinates"
    assert _extent(row) == (-0.5, 0.5, -0.5, 0.5, 0.0, 1.0)


def test_batch_bounds_leaves_a_body_with_an_unreadable_mapped_item_to_tessellation() -> None:
    ifc, wall = _wall_with_mapped_box()
    [representation] = wall.Representation.Representations
    [mapped] = representation.Items
    unreadable = ifc.createIfcMappedItem(
        mapped.MappingSource,
        ifc.createIfcCartesianTransformationOperator2D(
            None, None, ifc.createIfcCartesianPoint((3000.0, 0.0)), None
        ),
    )
    representation.Items = [mapped.MappingSource.MappedRepresentation.Items[0], unreadable]

    [parametric_row] = extract_element_bounds_batch(ifc, threads=1, prefer_parametric=True).bounds
    [tessellated_row] = extract_element_bounds_batch(ifc, threads=1, prefer_parametric=False).bounds

    assert parametric_row["source"] == "ifcopenshell.geom world coordinates"
    assert _extent(parametric_row) == _extent(tessellated_row)


def test_batch_bounds_leaves_an_unreadable_profile_placement_to_tessellation() -> None:
    ifc = ifcopenshell.api.project.create_file(version="IFC4X3")
    ifcopenshell.api.root.create_entity(ifc, ifc_class="IfcProject")
    ifcopenshell.api.unit.assign_unit(ifc)
    model = ifcopenshell.api.context.add_context(ifc, context_type="Model")
    body = ifcopenshell.api.context.add_context(
        ifc, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=model
    )
    curve = ifc.createIfcPolyline(
        [ifc.createIfcCartesianPoint((0.0, 0.0)), ifc.createIfcCartesianPoint((10000.0, 0.0))]
    )
    location = ifc.createIfcPointByDistanceExpression(
        ifc.createIfcLengthMeasure(5000.0), None, None, None, curve
    )
    profile = ifc.createIfcRectangleProfileDef(
        "AREA", None, ifc.createIfcAxis2Placement2D(location), 1000.0, 1000.0
    )
    solid = ifc.createIfcExtrudedAreaSolid(
        profile,
        ifc.createIfcAxis2Placement3D(ifc.createIfcCartesianPoint((0.0, 0.0, 0.0))),
        ifc.createIfcDirection((0.0, 0.0, 1.0)),
        1000.0,
    )
    wall = ifcopenshell.api.root.create_entity(ifc, ifc_class="IfcWall")
    wall.ObjectPlacement = ifc.createIfcLocalPlacement(
        None, ifc.createIfcAxis2Placement3D(ifc.createIfcCartesianPoint((0.0, 0.0, 0.0)))
    )
    wall.Representation = ifc.createIfcProductDefinitionShape(
        None, None, [ifc.createIfcShapeRepresentation(body, "Body", "SweptSolid", [solid])]
    )

    [parametric_row] = extract_element_bounds_batch(ifc, threads=1, prefer_parametric=True).bounds
    [tessellated_row] = extract_element_bounds_batch(ifc, threads=1, prefer_parametric=False).bounds

    assert parametric_row["source"] == "ifcopenshell.geom world coordinates"
    assert _extent(parametric_row) == _extent(tessellated_row)


def test_batch_bounds_leaves_a_mapped_item_with_a_2d_origin_to_tessellation() -> None:
    ifc, wall = _wall_with_mapped_box()
    mapped = wall.Representation.Representations[0].Items[0]
    mapped.MappingSource.MappingOrigin.Location = ifc.createIfcCartesianPoint((0.0, 0.0))

    result = extract_element_bounds_batch(ifc, threads=1, prefer_parametric=True)

    assert [row["source"] for row in result.bounds] == ["ifcopenshell.geom world coordinates"]


def test_batch_bounds_leaves_an_object_placement_with_a_2d_location_to_tessellation() -> None:
    ifc, wall = _wall_with_mapped_box()
    wall.ObjectPlacement.RelativePlacement.Location = ifc.createIfcCartesianPoint((0.0, 0.0))

    result = extract_element_bounds_batch(ifc, threads=1, prefer_parametric=True)

    assert [row["source"] for row in result.bounds] == ["ifcopenshell.geom world coordinates"]


def test_batch_bounds_tessellates_a_tapered_extrusion() -> None:
    ifc, wall = _wall_with_mapped_box()
    box = (
        wall.Representation.Representations[0].Items[0].MappingSource.MappedRepresentation.Items[0]
    )
    tapered = ifc.createIfcExtrudedAreaSolidTapered(
        box.SweptArea,
        box.Position,
        box.ExtrudedDirection,
        box.Depth,
        ifc.createIfcRectangleProfileDef("AREA", None, None, 3000.0, 3000.0),
    )
    wall.Representation.Representations[0].Items = [tapered]

    [parametric_row] = extract_element_bounds_batch(ifc, threads=1, prefer_parametric=True).bounds
    [tessellated_row] = extract_element_bounds_batch(ifc, threads=1, prefer_parametric=False).bounds

    assert _extent(parametric_row) == _extent(tessellated_row)
    assert parametric_row["max_x_m"] == 1.5


def _wall_with_mapped_box(
    *,
    origin: tuple[float, float, float] = (0.0, 0.0, 0.0),
    axis1: tuple[float, float, float] | None = None,
    scale2: float | None = None,
    scale3: float | None = None,
) -> tuple[ifcopenshell.file, ifcopenshell.entity_instance]:
    ifc = ifcopenshell.api.project.create_file(version="IFC4")
    ifcopenshell.api.root.create_entity(ifc, ifc_class="IfcProject")
    ifcopenshell.api.unit.assign_unit(ifc)
    model = ifcopenshell.api.context.add_context(ifc, context_type="Model")
    body = ifcopenshell.api.context.add_context(
        ifc, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=model
    )
    profile = ifc.createIfcRectangleProfileDef(
        "AREA",
        None,
        ifc.createIfcAxis2Placement2D(ifc.createIfcCartesianPoint((0.0, 0.0))),
        1000.0,
        1000.0,
    )
    box = ifc.createIfcExtrudedAreaSolid(
        profile,
        ifc.createIfcAxis2Placement3D(ifc.createIfcCartesianPoint((0.0, 0.0, 0.0))),
        ifc.createIfcDirection((0.0, 0.0, 1.0)),
        1000.0,
    )
    representation_map = ifc.createIfcRepresentationMap(
        ifc.createIfcAxis2Placement3D(ifc.createIfcCartesianPoint(origin)),
        ifc.createIfcShapeRepresentation(body, "Body", "SweptSolid", [box]),
    )
    target = ifc.createIfcCartesianTransformationOperator3DnonUniform(
        ifc.createIfcDirection(axis1) if axis1 else None,
        None,
        ifc.createIfcCartesianPoint((0.0, 0.0, 0.0)),
        None,
        None,
        scale2,
        scale3,
    )
    wall = ifcopenshell.api.root.create_entity(ifc, ifc_class="IfcWall")
    wall.ObjectPlacement = ifc.createIfcLocalPlacement(
        None, ifc.createIfcAxis2Placement3D(ifc.createIfcCartesianPoint((0.0, 0.0, 0.0)))
    )
    wall.Representation = ifc.createIfcProductDefinitionShape(
        None,
        None,
        [
            ifc.createIfcShapeRepresentation(
                body,
                "Body",
                "MappedRepresentation",
                [ifc.createIfcMappedItem(representation_map, target)],
            )
        ],
    )
    return ifc, wall


def _extent(row: dict[str, Any]) -> tuple[float, ...]:
    return tuple(row[f"{bound}_{axis}_m"] for axis in "xyz" for bound in ("min", "max"))

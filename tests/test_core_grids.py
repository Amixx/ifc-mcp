"""Tests for grid geometry helpers."""

from __future__ import annotations

from collections.abc import Sequence

import ifcopenshell
import ifcopenshell.api.project
import ifcopenshell.api.root
import ifcopenshell.api.unit

from ifc_mcp.core import get_grid_axes, get_grid_extents


def test_get_grid_extents_transforms_polyline_points() -> None:
    ifc = _millimetre_file()
    grid = _grid(ifc, "grid-b", offset=(2.0, -1.0))
    _add_axis(ifc, grid, "UAxes", _polyline(ifc, [(0.0, 0.0), (10.0, 5.0)]))
    _add_axis(ifc, grid, "VAxes", _polyline(ifc, [(-4.0, 8.0, 2.0)]))
    _grid(ifc, "grid-a")

    assert get_grid_extents(ifc) == {
        "grid_global_ids": ["grid-b"],
        "axis_count": 2,
        "min_x_m": -0.002,
        "max_x_m": 0.012,
        "min_y_m": -0.001,
        "max_y_m": 0.007,
    }


def test_get_grid_extents_returns_none_without_grids() -> None:
    ifc = ifcopenshell.open("data/BasicHouse.ifc")

    assert get_grid_extents(ifc) is None


def test_get_grid_axes_reads_every_axis_list() -> None:
    ifc = _millimetre_file()
    grid = _grid(ifc, "grid-b")
    _add_axis(ifc, grid, "UAxes", _polyline(ifc, [(0.0, 0.0)]), tag="A")
    _add_axis(ifc, grid, "UAxes", _polyline(ifc, [(1.0, 0.0)]), tag="B")
    _add_axis(ifc, grid, "VAxes", _polyline(ifc, [(0.0, 1.0)]), tag="1")
    _add_axis(ifc, grid, "WAxes", _polyline(ifc, [(0.0, 2.0)]), tag="Z")
    _grid(ifc, "grid-a")

    assert [
        (row["grid_global_id"], row["axis_set"], row["axis_tag"]) for row in get_grid_axes(ifc)
    ] == [
        ("grid-b", "U", "A"),
        ("grid-b", "U", "B"),
        ("grid-b", "V", "1"),
        ("grid-b", "W", "Z"),
    ]


def test_get_grid_axes_keeps_an_untagged_axis_distinguishable() -> None:
    ifc = _millimetre_file()
    grid = _grid(ifc, "grid-a")
    _add_axis(ifc, grid, "UAxes", _polyline(ifc, [(0.0, 0.0)]), tag="A")
    _add_axis(ifc, grid, "UAxes", _polyline(ifc, [(1.0, 1.0)]), tag=None)

    assert [row["axis_tag"] for row in get_grid_axes(ifc)] == ["A", None]


def test_get_grid_axes_places_points_in_world_metres() -> None:
    ifc = _millimetre_file()
    grid = _grid(ifc, "grid-a", offset=(2.0, -1.0))
    _add_axis(ifc, grid, "UAxes", _polyline(ifc, [(0.0, 0.0), (10000.0, 0.0)]), tag="A")

    assert get_grid_axes(ifc)[0]["points_m"] == [[0.002, -0.001], [10.002, -0.001]]


def test_get_grid_axes_walks_an_indexed_poly_curve() -> None:
    ifc = _millimetre_file()
    grid = _grid(ifc, "grid-a")
    curve = _indexed_poly_curve(
        ifc, [(0.0, 0.0), (1000.0, 0.0), (4000.0, 0.0)], [ifc.createIfcLineIndex((2, 3))]
    )
    _add_axis(ifc, grid, "UAxes", curve, tag="A")

    assert get_grid_axes(ifc)[0]["points_m"] == [[1.0, 0.0], [4.0, 0.0]]


def test_get_grid_axes_names_a_curve_class_it_does_not_read_and_keeps_the_axis() -> None:
    ifc = _millimetre_file()
    grid = _grid(ifc, "grid-a")
    circle = ifc.createIfcCircle(
        ifc.createIfcAxis2Placement2D(ifc.createIfcCartesianPoint((0.0, 0.0))), 1000.0
    )
    _add_axis(ifc, grid, "UAxes", circle, tag="A")

    [row] = get_grid_axes(ifc)

    assert (row["axis_tag"], row["curve"], row["points_m"]) == ("A", "IfcCircle", [])


def test_get_grid_axes_names_the_arc_that_bends_an_axis_and_keeps_the_axis() -> None:
    ifc = _millimetre_file()
    grid = _grid(ifc, "grid-a")
    _add_axis(ifc, grid, "UAxes", _arc(ifc), tag="A")

    [row] = get_grid_axes(ifc)

    assert (row["axis_tag"], row["curve"], row["points_m"]) == ("A", "IfcArcIndex", [])


def test_get_grid_extents_skips_an_axis_stating_no_line() -> None:
    """A curved axis leaves the extents to the straight ones instead of emptying them."""
    ifc = _millimetre_file()
    grid = _grid(ifc, "grid-a")
    _add_axis(ifc, grid, "UAxes", _arc(ifc), tag="A")
    _add_axis(ifc, grid, "UAxes", _polyline(ifc, [(0.0, 0.0), (4000.0, 0.0)]), tag="B")

    extents = get_grid_extents(ifc)

    assert extents is not None
    assert (extents["axis_count"], extents["max_x_m"]) == (1, 4.0)


def _millimetre_file() -> ifcopenshell.file:
    ifc = ifcopenshell.api.project.create_file(version="IFC4")
    ifcopenshell.api.root.create_entity(ifc, ifc_class="IfcProject")
    ifcopenshell.api.unit.assign_unit(ifc)
    return ifc


def _grid(
    ifc: ifcopenshell.file, global_id: str, offset: tuple[float, float] = (0.0, 0.0)
) -> ifcopenshell.entity_instance:
    grid = ifcopenshell.api.root.create_entity(ifc, ifc_class="IfcGrid")
    grid.GlobalId = global_id
    grid.ObjectPlacement = ifc.createIfcLocalPlacement(
        None, ifc.createIfcAxis2Placement3D(ifc.createIfcCartesianPoint((*offset, 0.0)))
    )
    return grid


def _add_axis(
    ifc: ifcopenshell.file,
    grid: ifcopenshell.entity_instance,
    axes: str,
    curve: ifcopenshell.entity_instance,
    tag: str | None = "A",
) -> None:
    axis = ifc.createIfcGridAxis(tag, curve, True)
    setattr(grid, axes, [*(getattr(grid, axes) or []), axis])


def _polyline(
    ifc: ifcopenshell.file, points: Sequence[tuple[float, ...]]
) -> ifcopenshell.entity_instance:
    return ifc.createIfcPolyline([ifc.createIfcCartesianPoint(point) for point in points])


def _indexed_poly_curve(
    ifc: ifcopenshell.file,
    points: Sequence[tuple[float, float]],
    segments: Sequence[ifcopenshell.entity_instance],
) -> ifcopenshell.entity_instance:
    return ifc.createIfcIndexedPolyCurve(ifc.createIfcCartesianPointList2D(points), segments)


def _arc(ifc: ifcopenshell.file) -> ifcopenshell.entity_instance:
    return _indexed_poly_curve(
        ifc, [(0.0, 0.0), (1000.0, 500.0), (2000.0, 0.0)], [ifc.createIfcArcIndex((1, 2, 3))]
    )

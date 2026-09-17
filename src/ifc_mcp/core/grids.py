"""Grid geometry helpers."""

from __future__ import annotations

from typing import Any

import ifcopenshell.util.placement
import ifcopenshell.util.unit

U_AXES = "U"
V_AXES = "V"
W_AXES = "W"


def get_grid_axes(ifc: Any) -> list[dict[str, Any]]:
    """Return every IfcGridAxis with its label, its curve class and the line it runs along.

    `IfcGridAxis.AxisTag` carries the label a coordinator references ("1", "A"), and is
    the only place an axis label lives — `IfcGrid.Name` is a container name that Revit
    fills with a fixed string. `AxisTag` is optional, so an untagged axis carries a
    ``None`` tag rather than dropping out of the result.

    `points_m` holds the axis curve's control points in project world coordinates in
    metres, so two axes from the same file intersect where their lines cross. An axis
    whose curve is not a straight line this reads — an arc, or a class outside the two
    polyline forms — carries an empty `points_m` and names the geometry that stopped it
    in `curve`: the axis is still in the result, because an axis missing from it reads
    downstream as a grid that never carried the axis at all.
    """
    unit_scale = ifcopenshell.util.unit.calculate_unit_scale(ifc)
    rows: list[dict[str, Any]] = []
    for grid in sorted(ifc.by_type("IfcGrid"), key=lambda entity: str(entity.GlobalId)):
        matrix = ifcopenshell.util.placement.get_local_placement(grid.ObjectPlacement)
        for axis_set, axes in (
            (U_AXES, grid.UAxes or []),
            (V_AXES, grid.VAxes or []),
            (W_AXES, grid.WAxes or []),
        ):
            for axis in axes:
                tag = getattr(axis, "AxisTag", None)
                curve, points = _axis_geometry(axis)
                rows.append(
                    {
                        "grid_global_id": str(grid.GlobalId),
                        "axis_set": axis_set,
                        "axis_tag": str(tag) if tag is not None else None,
                        "curve": curve,
                        "points_m": [_to_world_xy(point, matrix, unit_scale) for point in points],
                    }
                )
    return rows


def get_grid_extents(ifc: Any) -> dict[str, Any] | None:
    """Return XY extents for IfcGrid axis points in metres."""
    axes = [row for row in get_grid_axes(ifc) if row["points_m"]]
    if not axes:
        return None
    xs = [x for row in axes for x, _ in row["points_m"]]
    ys = [y for row in axes for _, y in row["points_m"]]
    return {
        "grid_global_ids": sorted({str(row["grid_global_id"]) for row in axes}),
        "axis_count": len(axes),
        "min_x_m": _round_m(min(xs)),
        "max_x_m": _round_m(max(xs)),
        "min_y_m": _round_m(min(ys)),
        "max_y_m": _round_m(max(ys)),
    }


def _axis_geometry(axis: Any) -> tuple[str | None, list[tuple[float, float, float]]]:
    """The class of an axis curve and the control points of the line it runs along.

    The points are empty whenever the curve states no straight line, and `curve` then
    names what it states instead: the segment class where an indexed poly curve bends,
    the curve's own class where the class is one this does not read.
    """
    curve = getattr(axis, "AxisCurve", None)
    if curve is None:
        return (None, [])
    if curve.is_a("IfcPolyline"):
        return (curve.is_a(), [_coordinates(point.Coordinates) for point in curve.Points])
    if curve.is_a("IfcIndexedPolyCurve"):
        return _indexed_poly_curve_geometry(curve)
    return (curve.is_a(), [])


def _indexed_poly_curve_geometry(
    curve: Any,
) -> tuple[str | None, list[tuple[float, float, float]]]:
    """The control points of an IfcIndexedPolyCurve, in the order its segments walk them.

    An `IfcArcIndex` segment bends the axis between its control points, so the straight
    line through them is not the axis and no intersection taken from it would be the one
    a coordinator sees.
    """
    coordinates = [_coordinates(entry) for entry in curve.Points.CoordList]
    segments = curve.Segments or []
    if not segments:
        return (curve.is_a(), coordinates)
    indices: list[int] = []
    for segment in segments:
        if segment.is_a("IfcArcIndex"):
            return (segment.is_a(), [])
        for index in segment[0]:
            if not indices or indices[-1] != index:
                indices.append(int(index))
    return (curve.is_a(), [coordinates[index - 1] for index in indices])


def _coordinates(values: Any) -> tuple[float, float, float]:
    coordinates = [float(value) for value in values]
    z = coordinates[2] if len(coordinates) > 2 else 0.0
    return (coordinates[0], coordinates[1], z)


def _to_world_xy(point: tuple[float, float, float], matrix: Any, unit_scale: float) -> list[float]:
    x, y, z = point
    world_x = (
        float(matrix[0][0]) * x
        + float(matrix[0][1]) * y
        + float(matrix[0][2]) * z
        + float(matrix[0][3])
    )
    world_y = (
        float(matrix[1][0]) * x
        + float(matrix[1][1]) * y
        + float(matrix[1][2]) * z
        + float(matrix[1][3])
    )
    return [_round_m(world_x * unit_scale), _round_m(world_y * unit_scale)]


def _round_m(value: float) -> float:
    return round(float(value), 3)

"""Grid geometry helpers."""

from __future__ import annotations

from typing import Any

import ifcopenshell.util.unit

from .ifc_util import get_grid_axis_coordinates

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
    in `curve`: the segment class where an indexed poly curve bends, the curve's own
    class otherwise. The axis is still in the result, because an axis missing from it
    reads downstream as a grid that never carried the axis at all.
    """
    unit_scale = ifcopenshell.util.unit.calculate_unit_scale(ifc)
    rows: list[dict[str, Any]] = []
    for grid in sorted(ifc.by_type("IfcGrid"), key=lambda entity: str(entity.GlobalId)):
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
                        "points_m": [
                            [_round_m(x * unit_scale), _round_m(y * unit_scale)]
                            for x, y, _ in points
                        ],
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


def _axis_geometry(axis: Any) -> tuple[str | None, list[list[float]]]:
    curve = axis.AxisCurve
    if curve is None:
        return (None, [])
    points = get_grid_axis_coordinates(axis)
    if points is not None:
        return (curve.is_a(), points.tolist())
    if curve.is_a("IfcIndexedPolyCurve"):
        return ("IfcArcIndex", [])
    return (curve.is_a(), [])


def _round_m(value: float) -> float:
    return round(float(value), 3)

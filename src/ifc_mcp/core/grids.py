"""Grid geometry helpers."""

from __future__ import annotations

from typing import Any

import ifcopenshell.util.placement
import ifcopenshell.util.unit


def get_grid_extents(ifc: Any) -> dict[str, Any] | None:
    """Return XY extents for IfcGrid axis polyline points in metres."""
    unit_scale = ifcopenshell.util.unit.calculate_unit_scale(ifc)
    xs: list[float] = []
    ys: list[float] = []
    grid_ids: list[str] = []
    axis_count = 0
    for grid in ifc.by_type("IfcGrid"):
        matrix = ifcopenshell.util.placement.get_local_placement(grid.ObjectPlacement)
        grid_used = False
        for axes in (grid.UAxes or [], grid.VAxes or [], grid.WAxes or []):
            for axis in axes:
                curve = getattr(axis, "AxisCurve", None)
                if not curve or not curve.is_a("IfcPolyline"):
                    continue
                axis_count += 1
                grid_used = True
                for point in curve.Points:
                    coords = list(point.Coordinates)
                    z = float(coords[2]) if len(coords) > 2 else 0.0
                    x = (
                        float(matrix[0][0]) * float(coords[0])
                        + float(matrix[0][1]) * float(coords[1])
                        + float(matrix[0][2]) * z
                        + float(matrix[0][3])
                    )
                    y = (
                        float(matrix[1][0]) * float(coords[0])
                        + float(matrix[1][1]) * float(coords[1])
                        + float(matrix[1][2]) * z
                        + float(matrix[1][3])
                    )
                    xs.append(x * unit_scale)
                    ys.append(y * unit_scale)
        if grid_used:
            grid_ids.append(grid.GlobalId)
    if not xs or not ys:
        return None
    return {
        "grid_global_ids": sorted(grid_ids),
        "axis_count": axis_count,
        "min_x_m": _round_m(min(xs)),
        "max_x_m": _round_m(max(xs)),
        "min_y_m": _round_m(min(ys)),
        "max_y_m": _round_m(max(ys)),
    }


def _round_m(value: float) -> float:
    return round(float(value), 3)

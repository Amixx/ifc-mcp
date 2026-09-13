"""Site placement helpers."""

from __future__ import annotations

import math
from typing import Any

import ifcopenshell.util.placement
import ifcopenshell.util.unit


def get_site_coordinates(ifc: Any) -> dict[str, Any] | None:
    """Return where the file places its site, in the file's own unit and in metres.

    The values come from the translation column of the `IfcSite` object placement
    resolved to world coordinates, so they are the origin every element in the file is
    positioned against. They are reported three ways — `x_raw` as the file states it,
    `x_m` and `x_mm` converted through `unit_scale_to_m` — because a caller comparing
    them against a coordinate stated in a document needs the unit the document uses,
    and a caller reasoning about the file's own numbers needs the unit the file uses.

    `rotation_deg` is the rotation of that placement about Z, measured counterclockwise
    from the +X axis. `true_north_deg` is the direction the file calls north, taken from
    the first `IfcGeometricRepresentationContext` that states a `TrueNorth` direction,
    measured clockwise from +Y; it is ``None`` when no context states one, which is what
    a file that never declares north looks like.

    The first `IfcSite` the file declares is the one read. ``None`` comes back when the
    file declares no site at all: nothing states where the project sits.
    """
    sites = ifc.by_type("IfcSite")
    if not sites:
        return None
    site = sites[0]
    unit_scale = ifcopenshell.util.unit.calculate_unit_scale(ifc)
    matrix = ifcopenshell.util.placement.get_local_placement(site.ObjectPlacement)
    raw = [float(matrix[0][3]), float(matrix[1][3]), float(matrix[2][3])]
    metres = [value * unit_scale for value in raw]
    return {
        "global_id": str(site.GlobalId),
        "name": getattr(site, "Name", None),
        "unit_scale_to_m": unit_scale,
        "x_raw": raw[0],
        "y_raw": raw[1],
        "z_raw": raw[2],
        "x_m": metres[0],
        "y_m": metres[1],
        "z_m": metres[2],
        "x_mm": metres[0] * 1000,
        "y_mm": metres[1] * 1000,
        "z_mm": metres[2] * 1000,
        "rotation_deg": _placement_rotation_deg(matrix),
        "true_north_deg": _true_north_deg(ifc),
    }


def _placement_rotation_deg(matrix: Any) -> float:
    angle = math.degrees(math.atan2(float(matrix[1][0]), float(matrix[0][0])))
    return round(angle % 360.0, 4)


def _true_north_deg(ifc: Any) -> float | None:
    """The direction the file calls north, clockwise from +Y, or None when none is stated.

    A `TrueNorth` whose direction ratios are both zero points nowhere, and a context
    carrying fewer than two ratios states no direction in the XY plane; neither is north,
    so the search continues to the next context rather than reading an angle out of them.
    """
    for context in ifc.by_type("IfcGeometricRepresentationContext"):
        true_north = getattr(context, "TrueNorth", None)
        ratios = getattr(true_north, "DirectionRatios", None)
        if not ratios or len(ratios) < 2:
            continue
        x = float(ratios[0])
        y = float(ratios[1])
        if x == 0.0 and y == 0.0:
            continue
        return round(math.degrees(math.atan2(x, y)), 4)
    return None

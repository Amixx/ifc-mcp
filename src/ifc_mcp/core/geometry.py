"""Geometry helpers independent from MCP/lint/diff layers."""

from __future__ import annotations

from typing import Any

import ifcopenshell
import ifcopenshell.util.placement


def extract_element_bounds(file_path: str, global_id: str) -> dict[str, list[float]] | None:
    """Compute geometry bounds for one element by GlobalId from IFC file."""
    try:
        ifc = ifcopenshell.open(file_path)
    except Exception:
        return None

    try:
        element = ifc.by_guid(global_id)
    except Exception:
        element = None
    if element is None:
        return None

    bounds = _extract_bounds_from_shape(element)
    if bounds is not None:
        return bounds
    return _extract_bounds_from_placement(element)


def _extract_bounds_from_shape(element: Any) -> dict[str, list[float]] | None:
    """Extract bounds via on-demand tessellation for one element."""
    try:
        import ifcopenshell.geom  # pylint: disable=import-outside-toplevel

        settings = ifcopenshell.geom.settings()
        settings.set("use-world-coords", True)
        settings.set("disable-opening-subtractions", True)
        settings.set("keep-bounding-boxes", True)
        shape = ifcopenshell.geom.create_shape(settings, element)
        vertices = list(getattr(shape.geometry, "verts", []) or [])
    except Exception:
        return None

    if not vertices:
        return None

    xs = vertices[0::3]
    ys = vertices[1::3]
    zs = vertices[2::3]
    if not xs or not ys or not zs:
        return None

    return {
        "min": [min(xs), min(ys), min(zs)],
        "max": [max(xs), max(ys), max(zs)],
    }


def _extract_bounds_from_placement(element: Any) -> dict[str, list[float]] | None:
    """Fallback to degenerate bounds at placement origin."""
    placement = getattr(element, "ObjectPlacement", None)
    if placement is None:
        return None

    try:
        matrix = ifcopenshell.util.placement.get_local_placement(placement)
    except Exception:
        return None

    x, y, z = float(matrix[0][3]), float(matrix[1][3]), float(matrix[2][3])
    return {"min": [x, y, z], "max": [x, y, z]}

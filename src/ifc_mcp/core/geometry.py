"""Geometry helpers independent from MCP/lint/diff layers."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import ifcopenshell
import ifcopenshell.util.placement
import ifcopenshell.util.unit


@dataclass(frozen=True)
class BoundsExtractionResult:
    """Targeted bounds plus diagnostics for elements that could not be bounded."""

    bounds: list[dict[str, Any]]
    diagnostics: list[dict[str, Any]]


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


def extract_element_bounds_batch(
    ifc: Any,
    *,
    include_classes: Iterable[str] | None = None,
    include_guids: Iterable[str] | None = None,
    threads: int = 4,
    prefer_parametric: bool = True,
) -> BoundsExtractionResult:
    """Compute targeted element bounds with cheap parametric extraction before tessellation.

    The parametric path handles common swept-solid representations without invoking
    OpenCascade. Remaining elements fall back to the IfcOpenShell geometry iterator.
    """

    class_filter = set(include_classes or [])
    guid_filter = set(include_guids or [])
    elements = [
        element
        for element in ifc.by_type("IfcElement")
        if _included(element, class_filter=class_filter, guid_filter=guid_filter)
    ]
    by_guid = {
        element.GlobalId: element for element in elements if getattr(element, "GlobalId", None)
    }
    unit_scale = ifcopenshell.util.unit.calculate_unit_scale(ifc)
    bounds_by_guid: dict[str, dict[str, Any]] = {}

    if prefer_parametric:
        for element in elements:
            guid = getattr(element, "GlobalId", None)
            if not guid:
                continue
            bounds = _extract_bounds_from_parametric_representation(element)
            if bounds is not None:
                bounds_by_guid[guid] = _bounds_row(
                    element,
                    _scale_bounds(bounds, unit_scale),
                    source="ifc parametric swept solid",
                    vertex_count=None,
                )

    remaining = [
        element
        for element in elements
        if getattr(element, "GlobalId", None)
        and getattr(element, "GlobalId", None) not in bounds_by_guid
    ]
    bounds_by_guid.update(_extract_bounds_with_iterator(ifc, remaining, by_guid, threads=threads))

    diagnostics = []
    for element in elements:
        guid = getattr(element, "GlobalId", None)
        if not guid or guid in bounds_by_guid:
            continue
        diagnostics.append(
            {
                "global_id": guid,
                "ifc_class": element.is_a(),
                "name": getattr(element, "Name", None),
                "tag": getattr(element, "Tag", None),
                "reason": _unbounded_reason(element),
            }
        )

    return BoundsExtractionResult(
        bounds=sorted(bounds_by_guid.values(), key=_sort_key),
        diagnostics=sorted(diagnostics, key=_sort_key),
    )


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


def _included(element: Any, *, class_filter: set[str], guid_filter: set[str]) -> bool:
    guid = getattr(element, "GlobalId", None)
    if guid_filter and guid not in guid_filter:
        return False
    return not class_filter or element.is_a() in class_filter


def _extract_bounds_with_iterator(
    ifc: Any,
    elements: list[Any],
    by_guid: dict[str, Any],
    *,
    threads: int,
) -> dict[str, dict[str, Any]]:
    bounds: dict[str, dict[str, Any]] = {}
    if not elements:
        return bounds

    try:
        import ifcopenshell.geom  # pylint: disable=import-outside-toplevel

        settings = ifcopenshell.geom.settings()
        settings.set("use-world-coords", True)
        settings.set("disable-opening-subtractions", True)
        settings.set("no-normals", True)
        iterator = ifcopenshell.geom.iterator(settings, ifc, max(1, threads), include=elements)
        if iterator.initialize():
            while True:
                shape = iterator.get()
                vertices = list(getattr(shape.geometry, "verts", []) or [])
                element = by_guid.get(shape.guid)
                if vertices and element is not None:
                    bounds[shape.guid] = _bounds_row(
                        element,
                        _bounds_from_vertices(vertices),
                        source="ifcopenshell.geom world coordinates",
                        vertex_count=len(vertices) // 3,
                    )
                if not iterator.next():
                    break
    except Exception:
        return bounds

    return bounds


def _extract_bounds_from_parametric_representation(element: Any) -> dict[str, list[float]] | None:
    try:
        element_matrix = ifcopenshell.util.placement.get_local_placement(element.ObjectPlacement)
    except Exception:
        return None

    collected: list[dict[str, list[float]]] = []
    representation = getattr(element, "Representation", None)
    for shape_representation in getattr(representation, "Representations", []) or []:
        for item in getattr(shape_representation, "Items", []) or []:
            item_bounds = _extract_item_bounds(item, element_matrix)
            if item_bounds is not None:
                collected.append(item_bounds)

    return _merge_bounds(collected)


def _extract_item_bounds(item: Any, parent_matrix: Any) -> dict[str, list[float]] | None:
    if item.is_a("IfcExtrudedAreaSolid"):
        return _extract_extruded_area_solid_bounds(item, parent_matrix)

    if item.is_a("IfcBooleanResult") or item.is_a("IfcBooleanClippingResult"):
        first_operand = getattr(item, "FirstOperand", None)
        if first_operand is not None:
            return _extract_item_bounds(first_operand, parent_matrix)
        return None

    if item.is_a("IfcMappedItem"):
        mapped_matrix = _matrix_multiply(parent_matrix, _mapped_item_matrix(item))
        mapped_representation = getattr(getattr(item, "MappingSource", None), "MappedRepresentation", None)
        child_bounds = [
            bounds
            for child in getattr(mapped_representation, "Items", []) or []
            if (bounds := _extract_item_bounds(child, mapped_matrix)) is not None
        ]
        return _merge_bounds(child_bounds)

    return None


def _extract_extruded_area_solid_bounds(
    item: Any, parent_matrix: Any
) -> dict[str, list[float]] | None:
    profile_points = _profile_points_2d(getattr(item, "SweptArea", None))
    if not profile_points:
        return None

    depth = float(getattr(item, "Depth", 0.0) or 0.0)
    direction = _direction_ratios(getattr(item, "ExtrudedDirection", None), default=(0.0, 0.0, 1.0))
    item_matrix = _matrix_multiply(parent_matrix, _axis2placement_matrix(getattr(item, "Position", None)))
    profile_matrix = _axis2placement_matrix(getattr(getattr(item, "SweptArea", None), "Position", None))
    item_matrix = _matrix_multiply(item_matrix, profile_matrix)
    points: list[tuple[float, float, float]] = []
    for x, y in profile_points:
        points.append(_transform_point(item_matrix, (x, y, 0.0)))
        points.append(
            _transform_point(
                item_matrix,
                (x + direction[0] * depth, y + direction[1] * depth, direction[2] * depth),
            )
        )
    return _bounds_from_points(points)


def _profile_points_2d(profile: Any) -> list[tuple[float, float]]:
    if profile is None:
        return []

    if profile.is_a("IfcRectangleProfileDef"):
        x = float(getattr(profile, "XDim", 0.0) or 0.0) / 2.0
        y = float(getattr(profile, "YDim", 0.0) or 0.0) / 2.0
        return [(-x, -y), (-x, y), (x, -y), (x, y)]

    if profile.is_a("IfcCircleProfileDef"):
        radius = float(getattr(profile, "Radius", 0.0) or 0.0)
        return [(-radius, -radius), (-radius, radius), (radius, -radius), (radius, radius)]

    if profile.is_a("IfcArbitraryClosedProfileDef"):
        return _curve_points_2d(getattr(profile, "OuterCurve", None))

    return []


def _curve_points_2d(curve: Any) -> list[tuple[float, float]]:
    if curve is None or not curve.is_a("IfcPolyline"):
        return []
    points = []
    for point in getattr(curve, "Points", []) or []:
        coords = list(getattr(point, "Coordinates", []) or [])
        if len(coords) >= 2:
            points.append((float(coords[0]), float(coords[1])))
    return points


def _mapped_item_matrix(item: Any) -> list[list[float]]:
    source = getattr(item, "MappingSource", None)
    origin = _axis2placement_matrix(getattr(source, "MappingOrigin", None))
    target = _cartesian_transformation_operator_matrix(getattr(item, "MappingTarget", None))
    return _matrix_multiply(target, _invert_rigid_matrix(origin))


def _axis2placement_matrix(placement: Any) -> list[list[float]]:
    if placement is None:
        return _identity_matrix()
    try:
        return ifcopenshell.util.placement.get_axis2placement(placement).tolist()
    except Exception:
        return _identity_matrix()


def _cartesian_transformation_operator_matrix(operator: Any) -> list[list[float]]:
    if operator is None:
        return _identity_matrix()

    scale = float(getattr(operator, "Scale", 1.0) or 1.0)
    axis1 = _direction_ratios(getattr(operator, "Axis1", None), default=(1.0, 0.0, 0.0))
    axis2 = _direction_ratios(getattr(operator, "Axis2", None), default=(0.0, 1.0, 0.0))
    axis3 = _direction_ratios(getattr(operator, "Axis3", None), default=_cross(axis1, axis2))
    origin = _cartesian_point(getattr(operator, "LocalOrigin", None), dimensions=3)
    return [
        [axis1[0] * scale, axis2[0] * scale, axis3[0] * scale, origin[0]],
        [axis1[1] * scale, axis2[1] * scale, axis3[1] * scale, origin[1]],
        [axis1[2] * scale, axis2[2] * scale, axis3[2] * scale, origin[2]],
        [0.0, 0.0, 0.0, 1.0],
    ]


def _direction_ratios(direction: Any, *, default: tuple[float, float, float]) -> tuple[float, float, float]:
    ratios = list(getattr(direction, "DirectionRatios", []) or [])
    if not ratios:
        return default
    values = [float(value) for value in ratios[:3]]
    while len(values) < 3:
        values.append(0.0)
    return (values[0], values[1], values[2])


def _cartesian_point(point: Any, *, dimensions: int) -> list[float]:
    coords = [float(value) for value in list(getattr(point, "Coordinates", []) or [])[:dimensions]]
    while len(coords) < dimensions:
        coords.append(0.0)
    return coords


def _cross(
    left: tuple[float, float, float], right: tuple[float, float, float]
) -> tuple[float, float, float]:
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def _identity_matrix() -> list[list[float]]:
    return [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]


def _matrix_multiply(left: Any, right: Any) -> list[list[float]]:
    return [
        [
            sum(float(left[row][index]) * float(right[index][column]) for index in range(4))
            for column in range(4)
        ]
        for row in range(4)
    ]


def _invert_rigid_matrix(matrix: Any) -> list[list[float]]:
    rotation_transpose = [[float(matrix[column][row]) for column in range(3)] for row in range(3)]
    translation = [float(matrix[row][3]) for row in range(3)]
    inverse_translation = [
        -sum(rotation_transpose[row][column] * translation[column] for column in range(3))
        for row in range(3)
    ]
    return [
        [*rotation_transpose[0], inverse_translation[0]],
        [*rotation_transpose[1], inverse_translation[1]],
        [*rotation_transpose[2], inverse_translation[2]],
        [0.0, 0.0, 0.0, 1.0],
    ]


def _transform_point(matrix: Any, point: tuple[float, float, float]) -> tuple[float, float, float]:
    x, y, z = point
    return (
        float(matrix[0][0]) * x + float(matrix[0][1]) * y + float(matrix[0][2]) * z + float(matrix[0][3]),
        float(matrix[1][0]) * x + float(matrix[1][1]) * y + float(matrix[1][2]) * z + float(matrix[1][3]),
        float(matrix[2][0]) * x + float(matrix[2][1]) * y + float(matrix[2][2]) * z + float(matrix[2][3]),
    )


def _bounds_from_vertices(vertices: list[float]) -> dict[str, list[float]]:
    return _bounds_from_points(list(zip(vertices[0::3], vertices[1::3], vertices[2::3], strict=False)))


def _bounds_from_points(points: list[tuple[float, float, float]]) -> dict[str, list[float]]:
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    zs = [point[2] for point in points]
    return {"min": [min(xs), min(ys), min(zs)], "max": [max(xs), max(ys), max(zs)]}


def _merge_bounds(bounds: list[dict[str, list[float]]]) -> dict[str, list[float]] | None:
    if not bounds:
        return None
    return {
        "min": [min(row["min"][axis] for row in bounds) for axis in range(3)],
        "max": [max(row["max"][axis] for row in bounds) for axis in range(3)],
    }


def _scale_bounds(bounds: dict[str, list[float]], scale: float) -> dict[str, list[float]]:
    return {
        "min": [value * scale for value in bounds["min"]],
        "max": [value * scale for value in bounds["max"]],
    }


def _bounds_row(
    element: Any,
    bounds: dict[str, list[float]],
    *,
    source: str,
    vertex_count: int | None,
) -> dict[str, Any]:
    row = {
        "global_id": element.GlobalId,
        "ifc_class": element.is_a(),
        "name": getattr(element, "Name", None),
        "tag": getattr(element, "Tag", None),
        "min_x_m": _round_m(bounds["min"][0]),
        "max_x_m": _round_m(bounds["max"][0]),
        "min_y_m": _round_m(bounds["min"][1]),
        "max_y_m": _round_m(bounds["max"][1]),
        "min_z_m": _round_m(bounds["min"][2]),
        "max_z_m": _round_m(bounds["max"][2]),
        "source": source,
    }
    if vertex_count is not None:
        row["vertex_count"] = vertex_count
    return row


def _unbounded_reason(element: Any) -> str:
    if not getattr(element, "Representation", None):
        return "element has no IfcProductRepresentation"
    return "ifcopenshell geometry iterator did not return bounded vertices"


def _sort_key(row: dict[str, Any]) -> tuple[Any, Any, Any]:
    return (row["ifc_class"], row["name"] or "", row["global_id"])


def _round_m(value: float) -> float:
    return round(float(value), 3)

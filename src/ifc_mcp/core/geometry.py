"""Geometry helpers independent from MCP/lint/diff layers."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

import ifcopenshell
import ifcopenshell.util.placement
import ifcopenshell.util.shape
import ifcopenshell.util.unit
import numpy as np


@dataclass(frozen=True)
class BoundsExtractionResult:
    """Targeted bounds, diagnostics for unbounded elements, and elements never scanned.

    ``diagnostics`` describes elements the extraction reached and could not bound — a
    property of the model, the same on every run. ``unscanned`` describes elements a
    caller-supplied ``time_budget_s`` cut off before the iterator reached them: which
    elements land there depends on how fast the machine was, so ``bounds`` is then a
    prefix of the model rather than the model.

    The two are separate because "this element has no usable geometry" and "this element
    was never looked at" are different claims, and a caller that publishes counts has to
    tell them apart. ``unscanned`` is empty whenever no time budget was set.
    """

    bounds: list[dict[str, Any]]
    diagnostics: list[dict[str, Any]]
    unscanned: list[dict[str, Any]] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        """Whether every requested element was scanned, so the counts describe the model."""
        return not self.unscanned


@dataclass(frozen=True)
class MeshExtractionResult:
    """Deduplicated local-space geometries plus per-element world-space instances.

    ``geometries`` is keyed by ifcopenshell's own ``shape.geometry.id`` -- elements that
    share an identical representation (the same window/door/column type at different
    placements) share one entry here and appear as separate rows in ``instances``. Callers
    should emit each geometry once and reference it by id per instance (e.g. glTF mesh +
    ``EXT_mesh_gpu_instancing``), not flatten it back to per-element world-space meshes.
    """

    geometries: dict[str, dict[str, Any]]
    instances: list[dict[str, Any]]
    diagnostics: list[dict[str, Any]]


def extract_element_bounds(file_path: str, global_id: str) -> dict[str, list[float]] | None:
    """Compute geometry bounds for one element by GlobalId from IFC file."""
    try:
        ifc = ifcopenshell.open(file_path)
    except (OSError, RuntimeError):
        return None

    try:
        element = ifc.by_guid(global_id)
    except RuntimeError:
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
    time_budget_s: float | None = None,
) -> BoundsExtractionResult:
    """Compute targeted element bounds with cheap parametric extraction before tessellation.

    The parametric path handles common swept-solid representations without invoking
    OpenCascade. Remaining elements fall back to the IfcOpenShell geometry iterator.

    By default the iterator runs to completion, so ``bounds`` and ``diagnostics`` are a
    function of the file alone: the same IFC yields the same two lists on every machine.

    Real Revit-exported architecture (many boolean opening subtractions) can make the
    iterator fallback take minutes per hundred elements rather than the sub-second cost
    typical of MEP/services content. A caller that cannot afford to wait may set
    ``time_budget_s`` to stop the iterator after that many seconds; the elements it never
    reached are then reported in ``unscanned`` rather than folded into ``diagnostics``,
    and ``complete`` is False. A wall clock makes the split between bounded and unbounded
    depend on machine load, so a caller that publishes either count must either leave
    ``time_budget_s`` unset or refuse to publish when ``complete`` is False.
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
    iterator_bounds, unscanned_guids = _extract_bounds_with_iterator(
        ifc, remaining, by_guid, threads=threads, time_budget_s=time_budget_s
    )
    bounds_by_guid.update(iterator_bounds)

    diagnostics = []
    unscanned = []
    for element in elements:
        guid = getattr(element, "GlobalId", None)
        if not guid or guid in bounds_by_guid:
            continue
        if guid in unscanned_guids:
            unscanned.append(_element_row(element, "geometry iterator time budget exceeded"))
        else:
            diagnostics.append(_element_row(element, _unbounded_reason(element)))

    return BoundsExtractionResult(
        bounds=sorted(bounds_by_guid.values(), key=_sort_key),
        diagnostics=sorted(diagnostics, key=_sort_key),
        unscanned=sorted(unscanned, key=_sort_key),
    )


def _element_row(element: Any, reason: str) -> dict[str, Any]:
    return {
        "global_id": element.GlobalId,
        "ifc_class": element.is_a(),
        "name": getattr(element, "Name", None),
        "tag": getattr(element, "Tag", None),
        "reason": reason,
    }


def extract_element_meshes_batch(
    ifc: Any,
    *,
    include_classes: Iterable[str] | None = None,
    include_guids: Iterable[str] | None = None,
    threads: int = 4,
    time_budget_s: float | None = None,
    linear_deflection: float | None = None,
    angular_deflection: float | None = None,
    exclude_openings: bool = False,
) -> MeshExtractionResult:
    """Tessellate elements into deduplicated local-space geometry plus per-instance world
    transforms, for real (triangulated) web rendering -- not just bounding boxes.

    Uses local (object-space) coordinates so identical representations produce byte-identical
    vertex/face buffers and collapse onto one ``geometry.id``; every production BIM web viewer
    with disclosed internals (SVF2, XKT, Speckle) leans on this kind of instance dedup, not
    spatial tiling, as its primary size lever for repetitive content (windows, doors, columns,
    duct fittings). ``time_budget_s`` bounds the OpenCascade tessellation pass the same way as
    :func:`extract_element_bounds_batch` -- real Revit architecture exports can be orders of
    magnitude slower per element than MEP/services content (measured: ~0.0009s/element vs.
    ~0.3s/element on real client files), so an unbounded pass is not safe to run inline.

    ``linear_deflection`` (metres of chord error, IfcOpenShell default 0.001) and
    ``angular_deflection`` (radians, default 0.5) select the mesher's fidelity, letting one
    caller build several level-of-detail tiers from the same file. Both default to ``None``,
    which leaves IfcOpenShell's own defaults untouched. They only affect geometry the mesher
    actually discretises: curved and swept surfaces respond, while representations whose
    curves were already flattened to explicit polylines/tessellations by the authoring tool
    (common in Revit MEP exports) hit a floor no deflection setting can push past -- callers
    that need to go below that floor must decimate the resulting triangles instead.

    ``exclude_openings`` drops ``IfcOpeningElement`` products from the output entirely and
    disables the boolean subtraction of openings from their host elements, so walls and
    slabs tessellate as solid uncut volumes. Windows and doors are separate products and
    still tessellate normally. Intended for orientation-grade viewers where hole fidelity
    does not matter; it also removes the phantom opening solids that would otherwise sit
    inside every cut.
    """
    class_filter = set(include_classes or [])
    guid_filter = set(include_guids or [])
    elements = [
        element
        for element in ifc.by_type("IfcElement")
        if _included(element, class_filter=class_filter, guid_filter=guid_filter)
        and not (exclude_openings and element.is_a("IfcOpeningElement"))
    ]
    by_guid = {
        element.GlobalId: element for element in elements if getattr(element, "GlobalId", None)
    }

    geometries: dict[str, dict[str, Any]] = {}
    instances: list[dict[str, Any]] = []
    visited_guids: set[str] = set()
    budget_expired = False

    try:
        import time as _time  # pylint: disable=import-outside-toplevel

        import ifcopenshell.geom  # pylint: disable=import-outside-toplevel

        settings = ifcopenshell.geom.settings()
        settings.set("use-world-coords", False)
        settings.set("weld-vertices", True)
        settings.set("apply-default-materials", True)
        if exclude_openings:
            settings.set("disable-opening-subtractions", True)
        if linear_deflection is not None:
            settings.set("mesher-linear-deflection", linear_deflection)
        if angular_deflection is not None:
            settings.set("mesher-angular-deflection", angular_deflection)

        deadline = _time.monotonic() + time_budget_s if time_budget_s is not None else None
        iterator = ifcopenshell.geom.iterator(settings, ifc, max(1, threads), include=elements)
        if iterator.initialize():
            while True:
                shape = iterator.get()
                visited_guids.add(shape.guid)
                element = by_guid.get(shape.guid)
                verts = shape.geometry.verts
                faces = shape.geometry.faces
                if element is not None and verts and faces:
                    geometry_id = shape.geometry.id
                    if geometry_id not in geometries:
                        geometries[geometry_id] = {
                            "positions": list(verts),
                            "indices": list(faces),
                        }
                    instances.append(
                        {
                            "global_id": shape.guid,
                            "ifc_class": element.is_a(),
                            "name": getattr(element, "Name", None),
                            "tag": getattr(element, "Tag", None),
                            "geometry_id": geometry_id,
                            "matrix": list(shape.transformation.matrix),
                            "color": _first_material_color(shape.geometry),
                        }
                    )
                if deadline is not None and _time.monotonic() >= deadline:
                    budget_expired = True
                    break
                if not iterator.next():
                    break
    except RuntimeError:
        pass

    instanced_guids = {row["global_id"] for row in instances}
    diagnostics = []
    for element in elements:
        guid = getattr(element, "GlobalId", None)
        if not guid or guid in instanced_guids:
            continue
        reason = (
            "geometry iterator time budget exceeded"
            if budget_expired and guid not in visited_guids
            else _unbounded_reason(element)
        )
        diagnostics.append(_element_row(element, reason))

    return MeshExtractionResult(
        geometries=geometries,
        instances=sorted(instances, key=lambda row: row["global_id"]),
        diagnostics=sorted(diagnostics, key=_sort_key),
    )


def _first_material_color(geometry: Any) -> list[float] | None:
    materials = getattr(geometry, "materials", None)
    if not materials:
        return None
    material = materials[0]
    diffuse = getattr(material, "diffuse", None)
    if diffuse is None:
        return None
    transparency = float(getattr(material, "transparency", 0.0) or 0.0)
    if not (0.0 <= transparency <= 1.0):
        transparency = 0.0
    return [float(diffuse.r()), float(diffuse.g()), float(diffuse.b()), 1.0 - transparency]


def _extract_bounds_from_shape(element: Any) -> dict[str, list[float]] | None:
    """Extract bounds via on-demand tessellation for one element."""
    try:
        import ifcopenshell.geom  # pylint: disable=import-outside-toplevel

        settings = ifcopenshell.geom.settings()
        settings.set("use-world-coords", True)
        settings.set("disable-opening-subtractions", True)
        settings.set("keep-bounding-boxes", True)
        shape: Any = ifcopenshell.geom.create_shape(settings, element)
        vertices = ifcopenshell.util.shape.get_vertices(shape.geometry)
    except RuntimeError:
        return None

    if not len(vertices):
        return None
    return _bounds_from_vertices(vertices)


def _extract_bounds_from_placement(element: Any) -> dict[str, list[float]] | None:
    """Fallback to degenerate bounds at placement origin."""
    placement = getattr(element, "ObjectPlacement", None)
    if placement is None:
        return None

    try:
        matrix = ifcopenshell.util.placement.get_local_placement(placement)
    except (AttributeError, RuntimeError, TypeError):
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
    time_budget_s: float | None = None,
) -> tuple[dict[str, dict[str, Any]], set[str]]:
    """Returns (bounds by guid, guids a time budget cut off before the iterator reached them).

    The second set is empty unless a budget was set and the clock actually ran out. An
    element the iterator ran past without yielding is unbounded on its own merits, not
    unscanned, so it belongs in the caller's diagnostics with its real reason.
    """
    import time as _time  # pylint: disable=import-outside-toplevel

    bounds: dict[str, dict[str, Any]] = {}
    seen_guids: set[str] = set()
    if not elements:
        return bounds, set()

    deadline = _time.monotonic() + time_budget_s if time_budget_s is not None else None
    budget_expired = False

    import ifcopenshell.geom  # pylint: disable=import-outside-toplevel

    settings = ifcopenshell.geom.settings()
    settings.set("use-world-coords", True)
    settings.set("disable-opening-subtractions", True)
    settings.set("no-normals", True)
    iterator = ifcopenshell.geom.iterator(settings, ifc, max(1, threads), include=elements)
    if iterator.initialize():
        while True:
            shape = iterator.get()
            seen_guids.add(shape.guid)
            vertices = ifcopenshell.util.shape.get_vertices(shape.geometry)
            element = by_guid.get(shape.guid)
            if len(vertices) and element is not None:
                bounds[shape.guid] = _bounds_row(
                    element,
                    _bounds_from_vertices(vertices),
                    source="ifcopenshell.geom world coordinates",
                    vertex_count=len(vertices),
                )
            if deadline is not None and _time.monotonic() >= deadline:
                budget_expired = True
                break
            if not iterator.next():
                break

    if not budget_expired:
        return bounds, set()

    unscanned = {
        guid
        for element in elements
        if (guid := getattr(element, "GlobalId", None)) and guid not in seen_guids
    }
    return bounds, unscanned


def _extract_bounds_from_parametric_representation(element: Any) -> dict[str, list[float]] | None:
    """Bounds of every Body item, or None when any one of them cannot be read parametrically."""
    try:
        element_matrix = ifcopenshell.util.placement.get_local_placement(element.ObjectPlacement)
    except (AttributeError, RuntimeError, TypeError, ValueError):
        return None

    representations = getattr(element.Representation, "Representations", None) or ()
    body = [r for r in representations if r.RepresentationIdentifier == "Body"]
    items = [item for representation in body for item in representation.Items]
    return _extract_all_item_bounds(items, element_matrix)


def _extract_all_item_bounds(items: Iterable[Any], matrix: np.ndarray) -> dict[str, Any] | None:
    collected = []
    for item in items:
        bounds = _extract_item_bounds(item, matrix)
        if bounds is None:
            return None
        collected.append(bounds)
    return _merge_bounds(collected)


def _extract_item_bounds(item: Any, parent_matrix: np.ndarray) -> dict[str, list[float]] | None:
    if item.is_a() == "IfcExtrudedAreaSolid":
        return _extract_extruded_area_solid_bounds(item, parent_matrix)

    if item.is_a("IfcBooleanResult"):
        operands = [item.FirstOperand]
        if item.Operator == "UNION":
            operands.append(item.SecondOperand)
        return _extract_all_item_bounds(operands, parent_matrix)

    if item.is_a("IfcMappedItem"):
        try:
            mapping = ifcopenshell.util.placement.get_mappeditem_transformation(item)
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return None
        if mapping is None:
            return None
        items = item.MappingSource.MappedRepresentation.Items
        return _extract_all_item_bounds(items, parent_matrix @ mapping)

    return None


def _extract_extruded_area_solid_bounds(
    item: Any, parent_matrix: np.ndarray
) -> dict[str, list[float]] | None:
    profile_points = _profile_points_2d(getattr(item, "SweptArea", None))
    if not profile_points:
        return None

    depth = float(getattr(item, "Depth", 0.0) or 0.0)
    direction = _direction_ratios(getattr(item, "ExtrudedDirection", None), default=(0.0, 0.0, 1.0))
    item_matrix = parent_matrix
    for placement in (item.Position, getattr(item.SweptArea, "Position", None)):
        if (matrix := _axis2placement_matrix(placement)) is None:
            return None
        item_matrix = item_matrix @ matrix
    points: list[tuple[float, float, float, float]] = []
    for x, y in profile_points:
        points.append((x, y, 0.0, 1.0))
        points.append(
            (x + direction[0] * depth, y + direction[1] * depth, direction[2] * depth, 1.0)
        )
    return _bounds_from_vertices((item_matrix @ np.array(points).T).T[:, :3])


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
    coords = [list(getattr(p, "Coordinates", []) or []) for p in getattr(curve, "Points", []) or []]
    return [(float(c[0]), float(c[1])) for c in coords if len(c) >= 2]


def _axis2placement_matrix(placement: Any) -> np.ndarray | None:
    if placement is None:
        return np.eye(4)
    try:
        return ifcopenshell.util.placement.get_axis2placement(placement)
    except (AttributeError, RuntimeError, TypeError, ValueError):
        return None


def _direction_ratios(
    direction: Any, *, default: tuple[float, float, float]
) -> tuple[float, float, float]:
    ratios = list(getattr(direction, "DirectionRatios", []) or [])
    if not ratios:
        return default
    values = [float(value) for value in ratios[:3]]
    while len(values) < 3:
        values.append(0.0)
    return (values[0], values[1], values[2])


def _bounds_from_vertices(vertices: np.ndarray) -> dict[str, list[float]]:
    low, high = ifcopenshell.util.shape.get_bbox(vertices)
    return {"min": low.tolist(), "max": high.tolist()}


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

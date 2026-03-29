"""Quantity and aggregation tools."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from ifc_mcp.core.index import ModelIndex


_AREA_KEYS = ["NetSideArea", "NetArea", "GrossArea", "Area"]
_VOLUME_KEYS = ["NetVolume", "GrossVolume", "Volume"]
_LENGTH_KEYS = ["Length", "NetLength", "GrossLength", "Perimeter"]


def get_quantities(
    index: ModelIndex,
    ifc_class: str | None = None,
    floor: str | None = None,
    material: str | None = None,
) -> dict[str, Any]:
    """Aggregate count/area/volume/length for elements matching optional filters."""
    class_filter = ifc_class.casefold() if ifc_class else None
    floor_filter = floor.casefold() if floor else None
    material_filter = material.casefold() if material else None

    selected = []
    for guid, entity in index.by_guid.items():
        if class_filter and entity.ifc_class.casefold() != class_filter:
            continue

        scene = index.get_scene(guid)
        if floor_filter:
            scene_floor = (scene.floor if scene else "") or ""
            if floor_filter not in scene_floor.casefold():
                continue

        if material_filter:
            names = [component.name.casefold() for component in entity.materials if component.name]
            if not any(material_filter in name for name in names):
                continue

        selected.append(entity)

    area = 0.0
    volume = 0.0
    length = 0.0

    for entity in selected:
        area += _quantity(entity, _AREA_KEYS) or 0.0
        volume += _quantity(entity, _VOLUME_KEYS) or _bbox_volume(entity) or 0.0
        length += _quantity(entity, _LENGTH_KEYS) or 0.0

    return {
        "count": len(selected),
        "total_area": round(area, 3),
        "total_volume": round(volume, 3),
        "total_length": round(length, 3),
    }


def get_material_summary(index: ModelIndex) -> dict[str, Any]:
    """Summarize material usage with counts, totals, and consuming types."""
    summary: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "element_count": 0,
            "total_area": 0.0,
            "total_volume": 0.0,
            "element_types": set(),
        }
    )
    covered_element_count = 0
    total_element_count = len(index.by_guid)

    for entity in index.by_guid.values():
        if not entity.materials:
            continue
        covered_element_count += 1

        area = _quantity(entity, _AREA_KEYS) or 0.0
        volume = _quantity(entity, _VOLUME_KEYS) or _bbox_volume(entity) or 0.0

        for component in entity.materials:
            row = summary[component.name]
            row["element_count"] += 1
            row["total_area"] += area
            row["total_volume"] += volume
            row["element_types"].add(entity.ifc_class)

    materials = []
    for material_name, row in summary.items():
        materials.append(
            {
                "material": material_name,
                "element_count": row["element_count"],
                "total_area": round(row["total_area"], 3),
                "total_volume": round(row["total_volume"], 3),
                "element_types": sorted(row["element_types"]),
            }
        )

    materials.sort(key=lambda item: item["material"])
    coverage = (covered_element_count / total_element_count) if total_element_count else 0.0
    return {
        "count": len(materials),
        "covered_element_count": covered_element_count,
        "total_element_count": total_element_count,
        "coverage": round(coverage, 6),
        "materials": materials,
    }


def get_space_summary(index: ModelIndex, floor: str | None = None) -> dict[str, Any]:
    """Summarize spaces with area, volume, and contained element counts."""
    floor_filter = floor.casefold() if floor else None

    contained_counts: dict[str, int] = defaultdict(int)
    for relation in index.relationships.get("spatial_containment", []):
        container_guid = relation.get("container_guid")
        if not container_guid:
            continue
        contained_counts[container_guid] += len(relation.get("element_guids", []))

    spaces = []
    for guid, entity in index.by_guid.items():
        if entity.ifc_class != "IfcSpace":
            continue

        scene = index.get_scene(guid)
        scene_floor = scene.floor if scene else None
        if floor_filter and floor_filter not in (scene_floor or "").casefold():
            continue

        area = _quantity(entity, _AREA_KEYS) or _quantity_from_pset(entity, "Pset_SpaceCommon", ["NetArea", "GrossArea"]) or 0.0
        volume = _quantity(entity, _VOLUME_KEYS) or _quantity_from_pset(entity, "Pset_SpaceCommon", ["NetVolume", "GrossVolume"]) or 0.0

        spaces.append(
            {
                "global_id": guid,
                "name": entity.name,
                "floor": scene_floor,
                "area": round(area, 3),
                "volume": round(volume, 3),
                "element_count": contained_counts.get(guid, 0),
            }
        )

    spaces.sort(key=lambda row: (row.get("floor") or "", row.get("name") or ""))
    return {"count": len(spaces), "spaces": spaces}


def _quantity(entity, keys: list[str]) -> float | None:
    for _, props in entity.property_sets.items():
        for key in keys:
            value = props.get(key)
            if isinstance(value, (int, float)):
                return float(value)
    return None


def _quantity_from_pset(entity, pset_name: str, keys: list[str]) -> float | None:
    props = entity.property_sets.get(pset_name, {})
    for key in keys:
        value = props.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return None


def _bbox_volume(entity) -> float | None:
    bounds = entity.geometry_bounds or {}
    mins = bounds.get("min")
    maxs = bounds.get("max")
    if not mins or not maxs:
        return None
    dx = maxs[0] - mins[0]
    dy = maxs[1] - mins[1]
    dz = maxs[2] - mins[2]
    if dx < 0 or dy < 0 or dz < 0:
        return None
    return dx * dy * dz

"""Element query tools."""

from __future__ import annotations

from typing import Any

from ifc_mcp.core.index import ModelIndex


def get_element_by_id(index: ModelIndex, global_id: str) -> dict[str, Any]:
    """Return full details for one element by GlobalId."""
    entity = index.entity_to_dict(global_id)
    if not entity:
        return {"error": f"Element not found: {global_id}"}
    return entity


def search_elements(
    index: ModelIndex,
    ifc_class: str | None = None,
    name: str | None = None,
    floor: str | None = None,
    material: str | None = None,
) -> dict[str, Any]:
    """Search elements with optional AND filters over class/name/floor/material."""
    class_filter = ifc_class.casefold() if ifc_class else None
    name_filter = name.casefold() if name else None
    floor_filter = floor.casefold() if floor else None
    material_filter = material.casefold() if material else None

    results: list[dict[str, Any]] = []

    for guid, entity in index.by_guid.items():
        if class_filter and entity.ifc_class.casefold() != class_filter:
            continue

        scene = index.get_scene(guid)

        if name_filter:
            haystack = f"{entity.name or ''} {scene.label if scene else ''}".casefold()
            if name_filter not in haystack:
                continue

        if floor_filter:
            scene_floor = (scene.floor if scene else None) or ""
            if floor_filter not in scene_floor.casefold():
                continue

        if material_filter:
            materials = [mat.name.casefold() for mat in entity.materials if mat.name]
            if not any(material_filter in mat for mat in materials):
                continue

        basic = index.basic_entity(guid)
        if basic:
            results.append(basic)

    return {"count": len(results), "results": results}


def get_element_properties(index: ModelIndex, global_id: str) -> dict[str, Any]:
    """Return all property sets for a specific element."""
    entity = index.get_entity(global_id)
    if not entity:
        return {"error": f"Element not found: {global_id}"}
    return entity.property_sets

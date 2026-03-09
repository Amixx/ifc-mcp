"""Spatial hierarchy and containment tools."""

from __future__ import annotations

from typing import Any

from ifc_mcp.core.index import ModelIndex


def get_spatial_structure(index: ModelIndex) -> dict[str, Any]:
    """Return full Site -> Building -> Storey -> Space hierarchy with counts."""
    return index.spatial_tree


def get_elements_in_space(index: ModelIndex, space_id: str) -> dict[str, Any]:
    """List all elements spatially contained in the given space/storey/container."""
    target_guid = _resolve_space_guid(index, space_id)
    if not target_guid:
        return {"error": f"Space/container not found: {space_id}", "results": []}

    contained_guids: set[str] = set()

    for relation in index.relationships.get("spatial_containment", []):
        if relation.get("container_guid") == target_guid:
            contained_guids.update(relation.get("element_guids", []))

    # Also include containment of child spaces when container is a storey/building/site.
    queue = [target_guid]
    visited: set[str] = set()
    while queue:
        current = queue.pop()
        if current in visited:
            continue
        visited.add(current)

        for relation in index.relationships.get("spatial_containment", []):
            if relation.get("container_guid") != current:
                continue
            for child in relation.get("element_guids", []):
                entity = index.get_entity(child)
                if entity and entity.ifc_class == "IfcSpace":
                    queue.append(child)
                contained_guids.add(child)

    results = [
        basic
        for guid in contained_guids
        if (basic := index.basic_entity(guid)) is not None
    ]

    results.sort(key=lambda row: (row.get("ifc_class") or "", row.get("name") or ""))
    return {
        "space_id": target_guid,
        "space_name": index.get_entity(target_guid).name if index.get_entity(target_guid) else None,
        "count": len(results),
        "results": results,
    }


def _resolve_space_guid(index: ModelIndex, space_id: str) -> str | None:
    """Resolve user-provided space/storey identifier to a GlobalId."""
    if space_id in index.by_guid:
        return space_id

    needle = space_id.casefold()
    for guid, entity in index.by_guid.items():
        if entity.ifc_class not in {"IfcSpace", "IfcBuildingStorey", "IfcBuilding", "IfcSite"}:
            continue
        if entity.name and entity.name.casefold() == needle:
            return guid

    return None

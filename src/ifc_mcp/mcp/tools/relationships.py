"""Relationship traversal tools."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from ifc_mcp.core.index import ModelIndex


def get_connected_elements(index: ModelIndex, global_id: str) -> dict[str, Any]:
    """Return elements connected through hosting, void/fill, or aggregation links."""
    if global_id not in index.by_guid:
        return {"error": f"Element not found: {global_id}", "connections": []}

    edges: list[dict[str, Any]] = []

    for row in index.connected.get(global_id, []):
        target = index.basic_entity(row["global_id"])
        if not target:
            continue
        edges.append({"relationship": row["relationship"], "element": target})

    # Resolve wall -> opening -> door/window into direct hosted relationship.
    opening_to_host = {
        relation["opening_guid"]: relation["element_guid"]
        for relation in index.relationships.get("voids", [])
    }
    opening_to_filler = {
        relation["opening_guid"]: relation["element_guid"]
        for relation in index.relationships.get("fills", [])
    }

    host_to_filler: dict[str, list[str]] = defaultdict(list)
    for opening, filler in opening_to_filler.items():
        host = opening_to_host.get(opening)
        if host:
            host_to_filler[host].append(filler)

    if global_id in host_to_filler:
        for filler in host_to_filler[global_id]:
            basic = index.basic_entity(filler)
            if basic:
                edges.append({"relationship": "hosts", "element": basic})

    for host, fillers in host_to_filler.items():
        if global_id in fillers:
            basic = index.basic_entity(host)
            if basic:
                edges.append({"relationship": "hosted_by", "element": basic})

    return {"global_id": global_id, "connections": edges}


def get_contained_elements(index: ModelIndex, global_id: str) -> dict[str, Any]:
    """Return child elements of a spatial or aggregate container."""
    if global_id not in index.by_guid:
        return {"error": f"Element not found: {global_id}", "children": []}

    children: list[dict[str, Any]] = []

    for relation in index.relationships.get("spatial_containment", []):
        if relation.get("container_guid") != global_id:
            continue
        for child in relation.get("element_guids", []):
            basic = index.basic_entity(child)
            if basic:
                children.append({"relationship": "spatial_contains", "element": basic})

    for relation in index.relationships.get("aggregates", []):
        if relation.get("parent_guid") != global_id:
            continue
        for child in relation.get("child_guids", []):
            basic = index.basic_entity(child)
            if basic:
                children.append({"relationship": "aggregates", "element": basic})

    return {"global_id": global_id, "count": len(children), "children": children}


def get_element_material(index: ModelIndex, global_id: str) -> dict[str, Any]:
    """Return assigned material layers/constituents for an element."""
    entity = index.get_entity(global_id)
    if not entity:
        return {"error": f"Element not found: {global_id}"}

    return {
        "global_id": global_id,
        "materials": [
            {
                "name": material.name,
                "thickness": material.thickness,
            }
            for material in entity.materials
        ],
    }

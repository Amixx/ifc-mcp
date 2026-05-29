"""Shared relationship-map helpers for element taxonomy tools."""

from __future__ import annotations

from typing import Any

from ifc_mcp.core.index import ModelIndex


def build_storey_containment_map(
    model: ModelIndex,
) -> tuple[set[str], dict[str, dict[str, Any]]]:
    """Return element GlobalIds directly contained by spatial structure."""
    cached = model.relationship_cache.get("storey_containment")
    if cached is not None:
        return cached

    contained_guids: set[str] = set()
    container_info_by_guid: dict[str, dict[str, Any]] = {}

    for relation in model.relationships.get("spatial_containment", []):
        container_guid = relation.get("container_guid")
        if not container_guid:
            continue
        container = model.get_entity(container_guid)
        container_info = {
            "global_id": container_guid,
            "ifc_class": container.ifc_class if container else None,
            "name": relation.get("container_name") or (container.name if container else None),
        }
        for child_guid in relation.get("element_guids", []):
            container_info_by_guid[child_guid] = container_info
            if container_info["ifc_class"] == "IfcBuildingStorey":
                contained_guids.add(child_guid)

    result = (contained_guids, container_info_by_guid)
    model.relationship_cache["storey_containment"] = result
    return result


def build_aggregate_map(model: ModelIndex) -> dict[str, str]:
    """Return aggregate child GlobalId to parent GlobalId map."""
    cached = model.relationship_cache.get("aggregate_child_to_parent")
    if cached is not None:
        return cached

    child_to_parent: dict[str, str] = {}
    for relation in model.relationships.get("aggregates", []):
        parent_guid = relation.get("parent_guid")
        if not parent_guid:
            continue
        for child_guid in relation.get("child_guids", []):
            child_to_parent[child_guid] = parent_guid

    model.relationship_cache["aggregate_child_to_parent"] = child_to_parent
    return child_to_parent


def has_direct_geometry(entity: Any) -> bool:
    """Return whether an IFC entity or indexed record has direct geometry."""
    representation = getattr(entity, "Representation", None)
    if representation is not None:
        return bool(getattr(representation, "Representations", None))

    attributes = getattr(entity, "attributes", {}) or {}
    if "has_direct_geometry" in attributes:
        return bool(attributes["has_direct_geometry"])

    return getattr(entity, "geometry_bounds", None) is not None

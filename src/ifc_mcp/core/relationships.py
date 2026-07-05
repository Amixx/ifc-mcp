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
            "name": relation.get("container_name")
            or (container.name if container else None),
        }
        for child_guid in relation.get("element_guids", []):
            container_info_by_guid[child_guid] = container_info
            if container_info["ifc_class"] == "IfcBuildingStorey":
                contained_guids.add(child_guid)

    result = (contained_guids, container_info_by_guid)
    model.relationship_cache["storey_containment"] = result
    return result


def resolve_storey_for_element(
    model: ModelIndex, global_id: str
) -> dict[str, Any] | None:
    """Return the IfcBuildingStorey containing an element, resolving through decomposition.

    Per IFC, an element decomposed into parts via ``IfcRelAggregates`` (e.g. a Revit layered
    floor or roof exported as a parent slab plus child layer-parts) carries no direct
    ``IfcRelContainedInSpatialStructure`` on the parts; the parts inherit the storey of their
    whole. ``build_storey_containment_map`` only reports *direct* containment, so callers that
    rely on it alone miss every decomposition part. This walks the aggregate chain upward from
    ``global_id`` until a storey container is found.

    Returns the container info dict (``global_id``/``ifc_class``/``name``) or ``None`` when the
    element resolves to no storey (e.g. it is contained directly under ``IfcBuilding``/``IfcSite``,
    or is a true orphan with neither containment nor an aggregate parent).
    """
    _, container_by_guid = build_storey_containment_map(model)
    child_to_parent = build_aggregate_map(model)
    seen: set[str] = set()
    guid: str | None = global_id
    while guid and guid not in seen:
        seen.add(guid)
        container = container_by_guid.get(guid)
        if container and container.get("ifc_class") == "IfcBuildingStorey":
            return container
        guid = child_to_parent.get(guid)
    return None


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

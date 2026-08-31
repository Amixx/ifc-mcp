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
    """Return the IfcBuildingStorey an element belongs to, walking the spatial hierarchy.

    ``build_storey_containment_map`` reports only the storey an element is *directly*
    contained by, and two common exports name the storey somewhere else:

    - An element decomposed into parts via ``IfcRelAggregates`` (a Revit layered floor
      exported as a parent slab plus child layer-parts) carries no
      ``IfcRelContainedInSpatialStructure`` on the parts; they inherit the storey of the whole.
    - A room-hosted family is contained in the ``IfcSpace`` it sits in, and the space —
      not the element — is what ``IfcRelAggregates`` places on the storey.

    So the walk follows both edges upward from ``global_id``: the aggregate parent where the
    node has one, otherwise the spatial element containing it, until a storey is reached.

    Returns the storey info dict (``global_id``/``ifc_class``/``name``) or ``None`` when the
    element resolves to no storey — it is contained directly under ``IfcBuilding``/``IfcSite``,
    sits in a space no storey aggregates, or is a true orphan with neither edge.
    """
    _, container_by_guid = build_storey_containment_map(model)
    child_to_parent = build_aggregate_map(model)
    seen: set[str] = set()
    guid: str | None = global_id
    while guid and guid not in seen:
        seen.add(guid)
        container = container_by_guid.get(guid)
        # A storey that contains the node outranks an aggregate parent that also holds it:
        # containment is the element's own spatial assignment, aggregation only its whole's.
        if container and container.get("ifc_class") == "IfcBuildingStorey":
            return container
        parent_guid = child_to_parent.get(guid) or (
            container["global_id"] if container else None
        )
        storey = _storey_record(model, parent_guid)
        if storey is not None:
            return storey
        guid = parent_guid
    return None


def _storey_record(model: ModelIndex, global_id: str | None) -> dict[str, Any] | None:
    """Describe a storey in the shape ``build_storey_containment_map`` returns, or None."""
    if not global_id:
        return None
    entity = model.get_entity(global_id)
    if entity is None or entity.ifc_class != "IfcBuildingStorey":
        return None
    return {
        "global_id": global_id,
        "ifc_class": entity.ifc_class,
        "name": entity.name,
    }


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

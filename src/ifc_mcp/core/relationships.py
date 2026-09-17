"""Shared relationship-map helpers for element taxonomy tools."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from ifc_mcp.core.index import ModelIndex
from ifc_mcp.core.types import MaterialComponent


def _iter_containments(model: ModelIndex) -> Iterator[tuple[str, dict[str, Any]]]:
    """Yield one ``(element GlobalId, container info)`` pair per containment edge."""
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
            yield child_guid, container_info


def build_storey_container_map(
    model: ModelIndex,
) -> dict[str, list[dict[str, Any]]]:
    """Return every IfcBuildingStorey each element is directly contained by.

    ``build_storey_containment_map`` keeps a single container per element, so a file that
    contains one element in two storeys — invalid under IFC, and something real exports
    and federated deliveries carry — is indistinguishable there from a correctly placed
    one. This map keeps one entry per ``IfcRelContainedInSpatialStructure`` edge that
    lands on a storey, so a caller can tell the two apart. Elements no storey contains
    directly are absent.
    """
    cached = model.relationship_cache.get("storey_containers")
    if cached is not None:
        return cached

    storeys_by_guid: dict[str, list[dict[str, Any]]] = {}
    for child_guid, container_info in _iter_containments(model):
        if container_info["ifc_class"] == "IfcBuildingStorey":
            storeys_by_guid.setdefault(child_guid, []).append(container_info)

    model.relationship_cache["storey_containers"] = storeys_by_guid
    return storeys_by_guid


def get_element_storey_placements(model: ModelIndex, ifc: Any) -> list[dict[str, Any]]:
    """Return every IfcElement the file declares with the storeys it is placed on.

    One row per element, carrying the identity a reader needs to find it again
    (``global_id``, ``ifc_class``, ``name``, ``tag``) and a ``storeys`` list holding the
    ``global_id`` and ``name`` of each storey it sits on.

    The direct containment edges are kept unmerged: an element two
    ``IfcRelContainedInSpatialStructure`` relations place on two storeys carries both, so a
    caller can see that the file says two things about where it is. Only an element no
    storey contains directly falls back to ``resolve_storey_for_element``, which walks the
    aggregate and spatial edges upward; an element that walk reaches no storey from carries
    an empty list.

    Every element is here, openings and decomposed parts included — which of them belong in
    an answer is the caller's question, not this one's. The exception is an element the file
    gives no GlobalId: a row is identified by that value, and an element without one cannot
    be found from a row, so it gets none.

    Rows come in the order the file declares the elements.
    """
    direct_containers = build_storey_container_map(model)
    rows: list[dict[str, Any]] = []
    for entity in ifc.by_type("IfcElement"):
        guid = entity.GlobalId
        if not guid:
            continue
        storeys = [
            {"global_id": storey["global_id"], "name": storey.get("name")}
            for storey in direct_containers.get(guid, [])
        ]
        if not storeys:
            container = resolve_storey_for_element(model, guid)
            if container is not None:
                storeys = [
                    {"global_id": container["global_id"], "name": container.get("name")}
                ]
        rows.append(
            {
                "global_id": guid,
                "ifc_class": entity.is_a(),
                "name": getattr(entity, "Name", None),
                "tag": getattr(entity, "Tag", None),
                "storeys": storeys,
            }
        )
    return rows


def build_storey_containment_map(
    model: ModelIndex,
) -> tuple[set[str], dict[str, dict[str, Any]]]:
    """Return element GlobalIds directly contained by spatial structure."""
    cached = model.relationship_cache.get("storey_containment")
    if cached is not None:
        return cached

    container_info_by_guid: dict[str, dict[str, Any]] = {}
    for child_guid, container_info in _iter_containments(model):
        container_info_by_guid[child_guid] = container_info

    result = (set(build_storey_container_map(model)), container_info_by_guid)
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


def get_effective_materials(model: ModelIndex, global_id: str) -> list[MaterialComponent]:
    """Collect material evidence on an occurrence, type, and aggregate descendants.

    Each source entity contributes once, even when a malformed graph reaches it twice.
    This is association evidence, not proof that every part has a material assignment.
    """
    cache_key = "material_aggregate_children"
    if cache_key not in model.relationship_cache:
        children: dict[str, list[str]] = {}
        for relation in model.relationships.get("aggregates", []):
            parent = relation.get("parent_guid")
            if parent:
                children.setdefault(parent, []).extend(relation.get("child_guids", []))
        model.relationship_cache[cache_key] = children
    children_by_parent = model.relationship_cache[cache_key]
    materials: list[MaterialComponent] = []
    pending = [global_id]
    visited: set[str] = set()
    sources: set[str] = set()
    while pending:
        guid = pending.pop()
        if guid in visited:
            continue
        visited.add(guid)
        entity = model.get_entity(guid)
        if entity is None:
            continue
        for source_guid in (guid, entity.type_guid):
            if not source_guid or source_guid in sources:
                continue
            source = model.get_entity(source_guid)
            if source is not None:
                materials.extend(source.materials)
                sources.add(source_guid)
        pending.extend(reversed(children_by_parent.get(guid, [])))
    return materials


def has_direct_geometry(entity: Any) -> bool:
    """Return whether an IFC entity or indexed record has direct geometry."""
    representation = getattr(entity, "Representation", None)
    if representation is not None:
        return bool(getattr(representation, "Representations", None))

    attributes = getattr(entity, "attributes", {}) or {}
    if "has_direct_geometry" in attributes:
        return bool(attributes["has_direct_geometry"])

    return getattr(entity, "geometry_bounds", None) is not None

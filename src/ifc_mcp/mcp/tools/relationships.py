"""Relationship traversal tools."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from ifc_mcp.core.index import ModelIndex, SPATIAL_CLASSES
from ifc_mcp.core.relationships import (
    build_aggregate_map,
    build_storey_containment_map,
    has_direct_geometry,
    resolve_storey_for_element,
)


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


def classify_elements_by_relation(
    index: ModelIndex,
    exclude_classes: list[str] | None = None,
) -> dict[str, Any]:
    """Classify IfcElement records as parent, child, or investigate.

    Returns {"summary": {...}, "elements": [...]} with relation category,
    parent GlobalId, spatial container metadata, and direct-geometry flag
    from IfcRelContainedInSpatialStructure and IfcRelAggregates.
    Based on parent-child element taxonomy by Kaspars Krauze, 2026.

    An element neither contained on a storey nor decomposed from a whole may still have a
    place in the model — a room-hosted family is contained in an ``IfcSpace`` that the
    storey aggregates — so ``investigate`` is reserved for the elements whose storey the
    spatial hierarchy cannot name at all. ``is_contained_in_building_storey`` reports
    direct containment only, so it stays False for such an element.
    """
    excluded = set(exclude_classes or [])
    storey_contained_guids, spatial_info_by_guid = build_storey_containment_map(index)
    child_to_parent = build_aggregate_map(index)

    elements: list[dict[str, Any]] = []
    excluded_count = 0
    category_counts: Counter[str] = Counter()

    for entity in sorted(_iter_ifc_elements(index), key=_entity_sort_key):
        if entity.ifc_class in excluded:
            excluded_count += 1
            continue

        is_storey_contained = entity.global_id in storey_contained_guids
        is_aggregate_child = entity.global_id in child_to_parent
        if is_storey_contained:
            category = "parent"
        elif is_aggregate_child:
            category = "child"
        elif resolve_storey_for_element(index, entity.global_id) is not None:
            category = "parent"
        else:
            category = "investigate"

        category_counts[category] += 1
        spatial_info = spatial_info_by_guid.get(entity.global_id) or {}
        elements.append(
            {
                "global_id": entity.global_id,
                "ifc_class": entity.ifc_class,
                "name": entity.name,
                "relation_category": category,
                "parent_global_id": child_to_parent.get(entity.global_id),
                "is_contained_in_building_storey": is_storey_contained,
                "is_aggregate_child": is_aggregate_child,
                "has_direct_geometry": has_direct_geometry(entity),
                "spatial_container_class": spatial_info.get("ifc_class"),
                "spatial_container_guid": spatial_info.get("global_id"),
                "spatial_container_name": spatial_info.get("name"),
            }
        )

    return {
        "summary": {
            "total_elements": len(elements),
            "parent_count": category_counts["parent"],
            "child_count": category_counts["child"],
            "investigate_count": category_counts["investigate"],
            "excluded_count": excluded_count,
        },
        "elements": elements,
    }


def get_aggregate_relationships(index: ModelIndex) -> dict[str, Any]:
    """Return aggregate parent/child relationships for fast lookup.

    Returns {"parents": {...}, "child_to_parent": {...}, "stats": {...}}
    with grouped child records and a flat child-to-parent map.
    Based on parent-child element taxonomy by Kaspars Krauze, 2026.
    """
    child_to_parent = build_aggregate_map(index)
    children_by_parent: dict[str, list[str]] = defaultdict(list)
    for child_guid, parent_guid in child_to_parent.items():
        children_by_parent[parent_guid].append(child_guid)

    parents: dict[str, dict[str, Any]] = {}
    for parent_guid in sorted(children_by_parent):
        parent = index.get_entity(parent_guid)
        children = [
            {
                "global_id": child.global_id,
                "ifc_class": child.ifc_class,
                "name": child.name,
            }
            for child_guid in sorted(children_by_parent[parent_guid])
            if (child := index.get_entity(child_guid)) is not None
        ]
        parents[parent_guid] = {
            "ifc_class": parent.ifc_class if parent else None,
            "name": parent.name if parent else None,
            "children": children,
        }

    return {
        "parents": parents,
        "child_to_parent": dict(sorted(child_to_parent.items())),
        "stats": {
            "parent_count": len(parents),
            "child_count": len(child_to_parent),
        },
    }


def find_orphans(
    index: ModelIndex,
    exclude_classes: list[str] | None = None,
) -> dict[str, Any]:
    """Find IfcElement records the spatial hierarchy places on no storey.

    Returns {"orphans": [...], "stats": {...}} with orphan records,
    diagnostics, direct-geometry flags, and count statistics by IFC class.
    Based on parent-child element taxonomy by Kaspars Krauze, 2026.

    An element contained in an ``IfcSpace`` the storey aggregates, or decomposed from a
    whole that is placed, is not an orphan: ``resolve_storey_for_element`` reaches a storey
    from it. Only the elements that route to none are reported.
    """
    excluded = set(exclude_classes or [])
    storey_contained_guids, _ = build_storey_containment_map(index)
    child_to_parent = build_aggregate_map(index)
    aggregate_parent_guids = set(child_to_parent.values())

    orphans: list[dict[str, Any]] = []
    by_class: Counter[str] = Counter()

    for entity in sorted(_iter_ifc_elements(index), key=_entity_sort_key):
        if entity.ifc_class in excluded:
            continue
        if entity.global_id in storey_contained_guids or entity.global_id in child_to_parent:
            continue
        if resolve_storey_for_element(index, entity.global_id) is not None:
            continue

        diagnostic = (
            "aggregate_orphan_no_storey"
            if entity.global_id in aggregate_parent_guids
            else "no_storey_no_aggregate"
        )
        by_class[entity.ifc_class] += 1
        orphans.append(
            {
                "global_id": entity.global_id,
                "ifc_class": entity.ifc_class,
                "name": entity.name,
                "has_direct_geometry": has_direct_geometry(entity),
                "diagnostic": diagnostic,
            }
        )

    return {
        "orphans": orphans,
        "stats": {
            "count": len(orphans),
            "by_class": dict(sorted(by_class.items())),
        },
    }


def _entity_sort_key(entity: Any) -> tuple[str, str, str]:
    return (entity.ifc_class or "", entity.name or "", entity.global_id)


def _iter_ifc_elements(index: ModelIndex) -> list[Any]:
    """Return indexed records that represent concrete IFC element occurrences."""
    excluded_exact = SPATIAL_CLASSES | {
        "IfcProject",
        "IfcTypeObject",
        "IfcGroup",
        "IfcZone",
        "IfcSpatialZone",
    }
    return [
        entity
        for entity in index.by_guid.values()
        if entity.ifc_class not in excluded_exact
        and not entity.ifc_class.startswith("IfcType")
        and not entity.ifc_class.endswith("Type")
    ]

"""Build a human-oriented scene model from parsed IFC data."""

from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import asdict
from typing import Any

from .types import EntityRecord, ParsedModel, SceneElement, SceneModel


_CLASS_CATEGORY = {
    "IfcWall": "wall",
    "IfcWallStandardCase": "wall",
    "IfcCurtainWall": "curtain wall",
    "IfcDoor": "door",
    "IfcWindow": "window",
    "IfcSlab": "floor slab",
    "IfcRoof": "roof",
    "IfcStair": "stair",
    "IfcStairFlight": "stair flight",
    "IfcRamp": "ramp",
    "IfcRampFlight": "ramp flight",
    "IfcRailing": "railing",
    "IfcColumn": "column",
    "IfcBeam": "beam",
    "IfcMember": "structural member",
    "IfcPlate": "plate",
    "IfcFooting": "footing",
    "IfcPile": "pile",
    "IfcFurnishingElement": "furniture",
    "IfcFurniture": "furniture",
    "IfcFlowTerminal": "fixture",
    "IfcSanitaryTerminal": "sanitary fixture",
    "IfcFlowSegment": "pipe/duct",
    "IfcDistributionPort": "port",
    "IfcOpeningElement": "opening",
    "IfcBuildingElementProxy": "element",
    "IfcGeographicElement": "landscape element",
    "IfcSite": "site element",
}

_SPATIAL_CLASSES = {"IfcSite", "IfcBuilding", "IfcBuildingStorey", "IfcSpace"}
_REVIT_NAME_RE = re.compile(r"^(.+):(.+):(\d+)$")
_REVIT_NAME_SHORT_RE = re.compile(r"^(.+):(\d{4,})$")
_AUTOGEN_NAME_RE = re.compile(r"^.+#\d+$")
_MFR_PREFIX_RE = re.compile(r"^[A-Z]_")
_DIMENSION_RE = re.compile(r"\d+\s*x\s*\d+(\s*x\s*\d+)*\s*mm\b")


def build_scene_model(parsed: ParsedModel | dict[str, Any]) -> SceneModel:
    """Build scene annotations and spatial hierarchy from parser output."""
    parsed_model = _coerce_parsed_model(parsed)
    entities = parsed_model.entities
    relationships = parsed_model.relationships

    hosting = _build_hosting_graph(relationships, entities)
    aggregation = _build_aggregation_graph(relationships, entities)
    spatial_tree, spatial_parent = _build_spatial_tree(parsed_model)

    guid_to_storey = _resolve_floor_lookup(entities, spatial_parent, aggregation["child_to_parent"])

    scene_elements: dict[str, SceneElement] = {}
    for guid, entity in entities.items():
        if entity.ifc_class in {"IfcProject", "IfcBuilding", "IfcSite"}:
            continue

        category = human_class(entity.ifc_class)
        orientation = _wall_orientation(entity) if category == "wall" else None
        is_external = _is_external(entity)
        floor = guid_to_storey.get(guid)

        scene_stub = {
            "guid": guid,
            "category": category,
            "name": clean_name(entity.name),
            "is_external": is_external,
            "orientation": orientation,
            "storey": floor,
            "host_guid": hosting["element_to_host"].get(guid),
            "hosted_guids": hosting["host_to_elements"].get(guid, []),
        }

        label = _generate_label(scene_stub, entities, guid_to_storey)

        scene_elements[guid] = SceneElement(
            global_id=guid,
            category=category,
            label=label,
            floor=floor,
            orientation=orientation,
            is_external=is_external,
            host_guid=hosting["element_to_host"].get(guid),
            hosted_guids=hosting["host_to_elements"].get(guid, []),
            parent_guid=aggregation["child_to_parent"].get(guid),
            child_guids=aggregation["parent_to_children"].get(guid, []),
        )

    return SceneModel(elements=scene_elements, spatial_tree=spatial_tree)


def build_scene(parsed: dict[str, Any]) -> dict[str, Any]:
    """Back-compat scene builder returning plain dictionaries."""
    scene = build_scene_model(parsed)
    return {
        "elements": {guid: asdict(element) for guid, element in scene.elements.items()},
        "spatial_tree": scene.spatial_tree,
    }


def human_class(ifc_class: str) -> str:
    """Convert an IFC class name to a human category name."""
    return _CLASS_CATEGORY.get(ifc_class, ifc_class.replace("Ifc", "").lower())


def _build_hosting_graph(
    relationships: dict[str, Any],
    entities: dict[str, EntityRecord],
) -> dict[str, dict[str, str] | dict[str, list[str]]]:
    """Resolve wall -> opening -> door/window into direct host mappings."""
    opening_to_wall: dict[str, str] = {}
    for relation in relationships.get("voids", []):
        opening_to_wall[relation["opening_guid"]] = relation["element_guid"]

    opening_to_filler: dict[str, str] = {}
    for relation in relationships.get("fills", []):
        opening_to_filler[relation["opening_guid"]] = relation["element_guid"]

    element_to_host: dict[str, str] = {}
    host_to_elements: dict[str, list[str]] = defaultdict(list)

    for opening_guid, filler_guid in opening_to_filler.items():
        wall_guid = opening_to_wall.get(opening_guid)
        if wall_guid and filler_guid in entities:
            element_to_host[filler_guid] = wall_guid
            host_to_elements[wall_guid].append(filler_guid)

    for opening_guid, wall_guid in opening_to_wall.items():
        if opening_guid in entities:
            element_to_host[opening_guid] = wall_guid

    return {
        "element_to_host": element_to_host,
        "host_to_elements": dict(host_to_elements),
    }


def _build_aggregation_graph(relationships: dict[str, Any], entities: dict[str, EntityRecord]) -> dict[str, Any]:
    """Build parent/child aggregation lookups from IfcRelAggregates."""
    parent_to_children: dict[str, list[str]] = defaultdict(list)
    child_to_parent: dict[str, str] = {}

    for relation in relationships.get("aggregates", []):
        parent_guid = relation["parent_guid"]
        for child_guid in relation.get("child_guids", []):
            if child_guid not in entities:
                continue
            parent_to_children[parent_guid].append(child_guid)
            child_to_parent[child_guid] = parent_guid

    return {
        "parent_to_children": dict(parent_to_children),
        "child_to_parent": child_to_parent,
    }


def _build_spatial_tree(parsed: ParsedModel) -> tuple[dict[str, Any], dict[str, str]]:
    """Build Site -> Building -> Storey -> Space hierarchy with element counts."""
    entities = parsed.entities
    relationships = parsed.relationships

    nodes: dict[str, dict[str, Any]] = {}
    parent_map: dict[str, str] = {}

    for guid, entity in entities.items():
        if entity.ifc_class not in _SPATIAL_CLASSES:
            continue
        nodes[guid] = {
            "global_id": guid,
            "name": entity.name,
            "ifc_class": entity.ifc_class,
            "children": [],
            "element_count": 0,
        }

    for relation in relationships.get("aggregates", []):
        parent_guid = relation["parent_guid"]
        if parent_guid not in nodes:
            continue
        for child_guid in relation.get("child_guids", []):
            if child_guid not in nodes:
                continue
            nodes[parent_guid]["children"].append(child_guid)
            parent_map[child_guid] = parent_guid

    for relation in relationships.get("spatial_containment", []):
        container_guid = relation.get("container_guid")
        if container_guid not in nodes:
            continue
        for guid in relation.get("element_guids", []):
            entity = entities.get(guid)
            if entity and entity.ifc_class == "IfcSpace" and guid in nodes and guid not in nodes[container_guid]["children"]:
                nodes[container_guid]["children"].append(guid)
                parent_map[guid] = container_guid

    direct_elements_by_spatial: dict[str, set[str]] = defaultdict(set)
    for relation in relationships.get("spatial_containment", []):
        container_guid = relation.get("container_guid")
        if container_guid not in nodes:
            continue
        for guid in relation.get("element_guids", []):
            entity = entities.get(guid)
            if not entity or entity.ifc_class in _SPATIAL_CLASSES:
                continue
            direct_elements_by_spatial[container_guid].add(guid)

    def count_descendants(node_guid: str) -> int:
        count = len(direct_elements_by_spatial.get(node_guid, set()))
        for child_guid in nodes[node_guid]["children"]:
            count += count_descendants(child_guid)
        nodes[node_guid]["element_count"] = count
        return count

    roots = [
        guid for guid, node in nodes.items() if node["ifc_class"] == "IfcSite" and guid not in parent_map
    ]
    if not roots:
        roots = [guid for guid in nodes if guid not in parent_map]

    for root_guid in roots:
        count_descendants(root_guid)

    def serialize_node(node_guid: str) -> dict[str, Any]:
        node = nodes[node_guid]
        return {
            "global_id": node["global_id"],
            "name": node["name"],
            "ifc_class": node["ifc_class"],
            "element_count": node["element_count"],
            "children": [serialize_node(child_guid) for child_guid in node["children"]],
        }

    tree = {
        "roots": [serialize_node(guid) for guid in roots],
        "total_spatial_nodes": len(nodes),
    }

    return tree, parent_map


def _resolve_floor_lookup(
    entities: dict[str, EntityRecord],
    spatial_parent: dict[str, str],
    aggregate_parent: dict[str, str],
) -> dict[str, str]:
    """Resolve each entity to nearest containing storey name when possible."""
    floor_by_guid: dict[str, str] = {}

    for guid, entity in entities.items():
        if entity.ifc_class == "IfcBuildingStorey" and entity.name:
            floor_by_guid[guid] = entity.name

    def walk_spatial_container(start_guid: str | None) -> str | None:
        current = start_guid
        seen: set[str] = set()
        while current and current not in seen:
            seen.add(current)
            container = entities.get(current)
            if not container:
                break
            if container.ifc_class == "IfcBuildingStorey":
                return container.name
            current = spatial_parent.get(current)
        return None

    changed = True
    while changed:
        changed = False
        for guid, entity in entities.items():
            if guid in floor_by_guid:
                continue

            floor = walk_spatial_container(entity.spatial_container)
            if not floor:
                parent = aggregate_parent.get(guid)
                if parent:
                    floor = floor_by_guid.get(parent)

            if floor:
                floor_by_guid[guid] = floor
                changed = True

    return floor_by_guid


def clean_name(name: str | None) -> str | None:
    """Normalize noisy names, especially Revit family/type/id variants."""
    if not name:
        return None
    if _AUTOGEN_NAME_RE.match(name):
        return None

    revit_match = _REVIT_NAME_RE.match(name)
    if revit_match:
        family, type_name, _ = revit_match.groups()
        if family == type_name:
            return _humanize_product_name(family)
        return _humanize_product_name(f"{family}: {type_name}")

    short_match = _REVIT_NAME_SHORT_RE.match(name)
    if short_match:
        return _humanize_product_name(short_match.group(1))

    return name


def _humanize_product_name(name: str) -> str | None:
    """Strip prefixes/dimensions to produce user-facing readable names."""
    name = _MFR_PREFIX_RE.sub("", name)
    name = _DIMENSION_RE.sub("", name)
    name = re.sub(r":\s*-\s*", " ", name)
    name = re.sub(r":\s*", " ", name)
    name = name.strip(" -")
    name = name.lower().replace("-", " ")
    name = re.sub(r"\s+", " ", name).strip()
    return name or None


def _is_external(entity: EntityRecord) -> bool | None:
    """Determine whether element is exterior from psets or name heuristics."""
    for _, props in entity.property_sets.items():
        if "IsExternal" in props:
            return bool(props["IsExternal"])

    combined = f"{entity.name or ''} {entity.type_name or ''}".lower()
    exterior_hints = ["exterior", "ytter", "outer", "facade", "façade", "external"]
    interior_hints = ["interior", "inner", "inre"]

    if any(hint in combined for hint in exterior_hints):
        return True
    if any(hint in combined for hint in interior_hints):
        return False
    return None


def _wall_orientation(entity: EntityRecord) -> str | None:
    """Compute nearest 8-point compass facing from wall local X axis."""
    placement = entity.placement
    if not placement:
        return None

    wall_dir_x = placement[0][0]
    wall_dir_y = placement[1][0]

    normal_x = -wall_dir_y
    normal_y = wall_dir_x

    length = math.hypot(normal_x, normal_y)
    if length < 0.001:
        return None

    angle = math.degrees(math.atan2(normal_x, normal_y))
    if angle < 0:
        angle += 360

    directions = [
        "north-facing",
        "northeast-facing",
        "east-facing",
        "southeast-facing",
        "south-facing",
        "southwest-facing",
        "west-facing",
        "northwest-facing",
    ]
    return directions[round(angle / 45) % 8]


def _generate_label(
    scene_stub: dict[str, Any],
    entities: dict[str, EntityRecord],
    guid_to_storey: dict[str, str],
) -> str:
    """Generate human-readable labels used by LLM tools and summaries."""
    category = scene_stub["category"]
    parts: list[str] = []

    if category == "wall":
        if scene_stub["is_external"] is True:
            parts.append("exterior")
        elif scene_stub["is_external"] is False:
            parts.append("interior")

        if scene_stub.get("orientation"):
            parts.append(scene_stub["orientation"])
        parts.append("wall")

    elif category in {"door", "window"}:
        host_guid = scene_stub.get("host_guid")
        if host_guid:
            host = entities.get(host_guid)
            host_external = _is_external(host) if host else None
            if host_external is True:
                parts.append("exterior")
            elif host_external is False:
                parts.append("interior")

        parts.append(category)

        if host_guid and host_guid in entities:
            host_orientation = _wall_orientation(entities[host_guid])
            if host_orientation:
                parts.append(f"in {host_orientation} wall")

    elif category == "opening":
        parts.append("opening in wall" if scene_stub.get("host_guid") else "opening")

    elif category in {"furniture", "fixture", "element"}:
        parts.append(scene_stub.get("name") or category)

    else:
        parts.append(category)

    label = " ".join(parts)
    floor = scene_stub.get("storey") or guid_to_storey.get(scene_stub["guid"])
    if floor:
        label = f"{label} ({floor})"

    return label


def _coerce_parsed_model(parsed: ParsedModel | dict[str, Any]) -> ParsedModel:
    """Accept ParsedModel or parser-compatible dict for compatibility."""
    if isinstance(parsed, ParsedModel):
        return parsed

    entities: dict[str, EntityRecord] = {}
    for guid, payload in parsed.get("entities", {}).items():
        entities[guid] = EntityRecord(
            global_id=guid,
            ifc_class=payload.get("ifc_class", "Unknown"),
            name=payload.get("name"),
            attributes=payload.get("attributes", {}),
            property_sets=payload.get("property_sets", {}),
            placement=payload.get("placement"),
            spatial_container=payload.get("container") or payload.get("spatial_container"),
            type_guid=payload.get("type_guid"),
            type_name=payload.get("type_name"),
            owner_history=payload.get("owner_history"),
            groups=payload.get("groups", []),
            materials=[],
            classifications=[],
            geometry_bounds=payload.get("geometry_bounds"),
        )

    return ParsedModel(
        metadata=parsed.get("metadata", {}),
        entities=entities,
        relationships=parsed.get("relationships", {}),
        duplicate_guids=parsed.get("duplicate_guids", []),
    )

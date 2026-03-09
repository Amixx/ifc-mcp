"""In-memory index built from parsed IFC data and scene annotations."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from .types import EntityRecord, ParsedModel, SceneElement, SceneModel


SPATIAL_CLASSES = {"IfcSite", "IfcBuilding", "IfcBuildingStorey", "IfcSpace"}


@dataclass(slots=True)
class ModelIndex:
    """Fast lookup index over parsed IFC entities and scene model annotations."""

    metadata: dict[str, Any]
    entities: dict[str, EntityRecord]
    scene_elements: dict[str, SceneElement]
    relationships: dict[str, Any]
    by_guid: dict[str, EntityRecord]
    by_type: dict[str, list[EntityRecord]]
    by_floor: dict[str, list[EntityRecord]]
    by_material: dict[str, list[EntityRecord]]
    by_space: dict[str, list[EntityRecord]]
    spatial_tree: dict[str, Any]
    type_map: dict[str, list[EntityRecord]]
    connected: dict[str, list[dict[str, str]]]
    duplicate_guids: list[str]
    source_file: str | None = None
    geometry_loaded: bool = True

    def get_entity(self, global_id: str) -> EntityRecord | None:
        """Fetch entity by GlobalId."""
        return self.by_guid.get(global_id)

    def get_scene(self, global_id: str) -> SceneElement | None:
        """Fetch scene element annotation by GlobalId."""
        return self.scene_elements.get(global_id)

    def entity_to_dict(self, global_id: str) -> dict[str, Any] | None:
        """Render full entity details for API/tool responses."""
        entity = self.by_guid.get(global_id)
        if not entity:
            return None

        scene = self.scene_elements.get(global_id)
        container = self.by_guid.get(entity.spatial_container) if entity.spatial_container else None
        type_entity = self.by_guid.get(entity.type_guid) if entity.type_guid else None

        return {
            "global_id": entity.global_id,
            "ifc_class": entity.ifc_class,
            "name": entity.name,
            "attributes": entity.attributes,
            "property_sets": entity.property_sets,
            "placement": entity.placement,
            "spatial_container": {
                "global_id": entity.spatial_container,
                "name": container.name if container else None,
                "ifc_class": container.ifc_class if container else None,
            }
            if entity.spatial_container
            else None,
            "type": {
                "global_id": entity.type_guid,
                "name": entity.type_name or (type_entity.name if type_entity else None),
                "property_sets": type_entity.property_sets if type_entity else {},
            }
            if entity.type_guid
            else None,
            "owner_history": entity.owner_history,
            "groups": entity.groups,
            "materials": [
                {"name": material.name, "thickness": material.thickness}
                for material in entity.materials
            ],
            "classifications": [
                {
                    "system": cref.system,
                    "reference": cref.reference,
                    "identification": cref.identification,
                }
                for cref in entity.classifications
            ],
            "geometry_bounds": entity.geometry_bounds,
            "scene_label": scene.label if scene else None,
            "floor": scene.floor if scene else None,
            "connected": self.connected.get(global_id, []),
        }

    def basic_entity(self, global_id: str) -> dict[str, Any] | None:
        """Render lightweight entity info used in list/search responses."""
        entity = self.by_guid.get(global_id)
        if not entity:
            return None
        scene = self.scene_elements.get(global_id)
        return {
            "global_id": entity.global_id,
            "ifc_class": entity.ifc_class,
            "name": entity.name,
            "floor": scene.floor if scene else None,
            "scene_label": scene.label if scene else None,
        }

    def get_summary(self) -> dict[str, Any]:
        """Build high-level model summary metadata and quantity rollups."""
        counts_by_class: dict[str, int] = defaultdict(int)
        total_area = 0.0

        for entity in self.entities.values():
            if entity.ifc_class.startswith("IfcType"):
                continue
            counts_by_class[entity.ifc_class] += 1
            area = _extract_quantity(entity, ["NetSideArea", "GrossArea", "NetArea", "Area"])
            if area is not None:
                total_area += area

        spaces = [entity for entity in self.entities.values() if entity.ifc_class == "IfcSpace"]

        return {
            "metadata": self.metadata,
            "counts_by_ifc_class": dict(sorted(counts_by_class.items())),
            "floor_count": len(self.by_floor),
            "total_spaces": len(spaces),
            "total_area": round(total_area, 3),
        }


def build_index(
    parsed: ParsedModel | dict[str, Any],
    scene: SceneModel | dict[str, Any],
    source_file: str | None = None,
    geometry_loaded: bool = True,
) -> ModelIndex:
    """Create the in-memory lookup index from parsed and scene model data."""
    parsed_model = _coerce_parsed_model(parsed)
    scene_model = _coerce_scene_model(scene)

    entities = parsed_model.entities

    by_type: dict[str, list[EntityRecord]] = defaultdict(list)
    by_floor: dict[str, list[EntityRecord]] = defaultdict(list)
    by_material: dict[str, list[EntityRecord]] = defaultdict(list)
    by_space: dict[str, list[EntityRecord]] = defaultdict(list)

    for guid, entity in entities.items():
        by_type[entity.ifc_class].append(entity)

        scene_element = scene_model.elements.get(guid)
        if scene_element and scene_element.floor:
            by_floor[scene_element.floor].append(entity)

        for material in entity.materials:
            if material.name:
                by_material[material.name].append(entity)

        if entity.spatial_container:
            container = entities.get(entity.spatial_container)
            if container and container.ifc_class == "IfcSpace":
                key = container.name or container.global_id
                by_space[key].append(entity)

    type_map: dict[str, list[EntityRecord]] = defaultdict(list)
    for relation in parsed_model.relationships.get("defines_by_type", []):
        type_guid = relation.get("type_guid")
        if not type_guid:
            continue
        for guid in relation.get("element_guids", []):
            entity = entities.get(guid)
            if entity:
                type_map[type_guid].append(entity)

    connected = _build_connected_map(parsed_model.relationships)

    return ModelIndex(
        metadata=parsed_model.metadata,
        entities=entities,
        scene_elements=scene_model.elements,
        relationships=parsed_model.relationships,
        by_guid=entities,
        by_type=dict(by_type),
        by_floor=dict(by_floor),
        by_material=dict(by_material),
        by_space=dict(by_space),
        spatial_tree=scene_model.spatial_tree,
        type_map=dict(type_map),
        connected=connected,
        duplicate_guids=parsed_model.duplicate_guids,
        source_file=source_file,
        geometry_loaded=geometry_loaded,
    )


def _build_connected_map(relationships: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    """Build adjacency map used by relationship traversal tools."""
    connected: dict[str, list[dict[str, str]]] = defaultdict(list)

    for relation in relationships.get("voids", []):
        host = relation["element_guid"]
        opening = relation["opening_guid"]
        connected[host].append({"global_id": opening, "relationship": "voids"})
        connected[opening].append({"global_id": host, "relationship": "voided_by"})

    for relation in relationships.get("fills", []):
        opening = relation["opening_guid"]
        filler = relation["element_guid"]
        connected[opening].append({"global_id": filler, "relationship": "fills"})
        connected[filler].append({"global_id": opening, "relationship": "filled_by"})

    for relation in relationships.get("aggregates", []):
        parent = relation["parent_guid"]
        for child in relation.get("child_guids", []):
            connected[parent].append({"global_id": child, "relationship": "contains"})
            connected[child].append({"global_id": parent, "relationship": "part_of"})

    for relation in relationships.get("spatial_containment", []):
        container = relation.get("container_guid")
        if not container:
            continue
        for child in relation.get("element_guids", []):
            connected[container].append({"global_id": child, "relationship": "spatial_contains"})
            connected[child].append({"global_id": container, "relationship": "spatially_contained_in"})

    return dict(connected)


def _extract_quantity(entity: EntityRecord, names: list[str]) -> float | None:
    """Find first numeric quantity from psets matching candidate names."""
    for _, props in entity.property_sets.items():
        for name in names:
            value = props.get(name)
            if isinstance(value, (int, float)):
                return float(value)
    return None


def _coerce_parsed_model(parsed: ParsedModel | dict[str, Any]) -> ParsedModel:
    """Accept ParsedModel instance or parser-like dictionary payload."""
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
            spatial_container=payload.get("spatial_container") or payload.get("container"),
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


def _coerce_scene_model(scene: SceneModel | dict[str, Any]) -> SceneModel:
    """Accept SceneModel instance or dictionary payload."""
    if isinstance(scene, SceneModel):
        return scene

    elements: dict[str, SceneElement] = {}
    for guid, payload in scene.get("elements", {}).items():
        elements[guid] = SceneElement(
            global_id=guid,
            category=payload.get("category", "element"),
            label=payload.get("label", guid),
            floor=payload.get("floor") or payload.get("storey"),
            orientation=payload.get("orientation"),
            is_external=payload.get("is_external"),
            host_guid=payload.get("host_guid"),
            hosted_guids=payload.get("hosted_guids", []),
            parent_guid=payload.get("parent_guid"),
            child_guids=payload.get("child_guids", []),
        )

    return SceneModel(elements=elements, spatial_tree=scene.get("spatial_tree", {}))

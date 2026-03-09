"""Extract structured entity data from IFC files."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from typing import Any

import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.placement

from .types import ClassificationReference, EntityRecord, MaterialComponent, ParsedModel


def parse_ifc(filepath: str) -> ParsedModel:
    """Parse an IFC file into normalized metadata, entities, and relationships."""
    ifc = ifcopenshell.open(filepath)

    group_map, group_relationships = _build_group_map(ifc)
    material_map, material_relationships = _build_material_map(ifc)
    classification_map, classification_relationships = _build_classification_map(ifc)
    type_map, type_relationships = _build_type_relationships(ifc)
    spatial_children, container_map, spatial_relationships = _build_spatial_relationships(ifc)
    defines_by_properties = _build_property_definition_relationships(ifc)
    voids, fills, aggregates = _extract_structural_relationships(ifc)

    entities: dict[str, EntityRecord] = {}
    duplicate_guids: list[str] = []

    for element in _iter_entity_candidates(ifc):
        guid = getattr(element, "GlobalId", None)
        if not guid:
            continue
        if guid in entities:
            duplicate_guids.append(guid)
            continue

        entities[guid] = EntityRecord(
            global_id=guid,
            ifc_class=element.is_a(),
            name=getattr(element, "Name", None),
            attributes=_extract_attributes(element),
            property_sets=_extract_psets(element),
            placement=_extract_placement(element),
            spatial_container=container_map.get(guid),
            type_guid=type_map.get(guid),
            type_name=_extract_type_name(ifc, type_map.get(guid)),
            owner_history=_extract_owner_history(element),
            groups=group_map.get(guid, []),
            materials=material_map.get(guid, []),
            classifications=classification_map.get(guid, []),
            geometry_bounds=_extract_geometry_bounds(element),
        )

    relationships: dict[str, Any] = {
        "voids": voids,
        "fills": fills,
        "aggregates": aggregates,
        "spatial_containment": spatial_relationships,
        "spatial_children": spatial_children,
        "assigns_to_group": group_relationships,
        "associates_material": material_relationships,
        "defines_by_type": type_relationships,
        "defines_by_properties": defines_by_properties,
        "associates_classification": classification_relationships,
    }

    return ParsedModel(
        metadata=_extract_metadata(ifc),
        entities=entities,
        relationships=relationships,
        duplicate_guids=sorted(set(duplicate_guids)),
    )


def parse(filepath: str) -> dict[str, Any]:
    """Back-compat parser function returning a plain dict."""
    parsed = parse_ifc(filepath)
    return {
        "metadata": parsed.metadata,
        "entities": {guid: _entity_to_dict(entity) for guid, entity in parsed.entities.items()},
        "relationships": parsed.relationships,
        "duplicate_guids": parsed.duplicate_guids,
    }


def _iter_entity_candidates(ifc) -> list[Any]:
    """Return entities that should be indexed by GlobalId."""
    entities: dict[str, Any] = {}
    for cls in ("IfcProduct", "IfcTypeObject", "IfcGroup"):
        for element in ifc.by_type(cls):
            guid = getattr(element, "GlobalId", None)
            if guid:
                entities[guid] = element
    return list(entities.values())


def _extract_structural_relationships(ifc) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, Any]]]:
    """Extract void/fill/aggregate relationships used by scene and tools."""
    voids: list[dict[str, str]] = []
    for rel in ifc.by_type("IfcRelVoidsElement"):
        element = rel.RelatingBuildingElement
        opening = rel.RelatedOpeningElement
        if hasattr(element, "GlobalId") and hasattr(opening, "GlobalId"):
            voids.append({"element_guid": element.GlobalId, "opening_guid": opening.GlobalId})

    fills: list[dict[str, str]] = []
    for rel in ifc.by_type("IfcRelFillsElement"):
        opening = rel.RelatingOpeningElement
        filler = rel.RelatedBuildingElement
        if hasattr(opening, "GlobalId") and hasattr(filler, "GlobalId"):
            fills.append({"opening_guid": opening.GlobalId, "element_guid": filler.GlobalId})

    aggregates: list[dict[str, Any]] = []
    for rel in ifc.by_type("IfcRelAggregates"):
        parent = rel.RelatingObject
        if not hasattr(parent, "GlobalId"):
            continue
        child_guids = [
            obj.GlobalId for obj in rel.RelatedObjects if hasattr(obj, "GlobalId")
        ]
        if child_guids:
            aggregates.append({"parent_guid": parent.GlobalId, "child_guids": child_guids})

    return voids, fills, aggregates


def _build_spatial_relationships(ifc) -> tuple[dict[str, list[str]], dict[str, str], list[dict[str, Any]]]:
    """Build spatial container relationships and element container lookup."""
    spatial_children: dict[str, list[str]] = defaultdict(list)
    container_map: dict[str, str] = {}
    rels: list[dict[str, Any]] = []

    for rel in ifc.by_type("IfcRelContainedInSpatialStructure"):
        container = rel.RelatingStructure
        if not hasattr(container, "GlobalId"):
            continue

        element_guids = [
            element.GlobalId for element in rel.RelatedElements if hasattr(element, "GlobalId")
        ]
        if not element_guids:
            continue

        rels.append(
            {
                "container_guid": container.GlobalId,
                "container_name": getattr(container, "Name", None),
                "element_guids": element_guids,
            }
        )
        spatial_children[container.GlobalId].extend(element_guids)

        for guid in element_guids:
            container_map[guid] = container.GlobalId

    return dict(spatial_children), container_map, rels


def _build_group_map(ifc) -> tuple[dict[str, list[str]], list[dict[str, Any]]]:
    """Build element -> group names from IfcRelAssignsToGroup."""
    group_map: dict[str, list[str]] = defaultdict(list)
    relationships: list[dict[str, Any]] = []

    for rel in ifc.by_type("IfcRelAssignsToGroup"):
        group = rel.RelatingGroup
        group_guid = getattr(group, "GlobalId", None)
        group_name = _strip_revit_trailing_id(getattr(group, "Name", None))
        related = [obj.GlobalId for obj in rel.RelatedObjects if hasattr(obj, "GlobalId")]

        if related:
            relationships.append(
                {
                    "group_guid": group_guid,
                    "group_name": group_name,
                    "element_guids": related,
                }
            )

        if not group_name:
            continue

        for guid in related:
            if group_name not in group_map[guid]:
                group_map[guid].append(group_name)

    return dict(group_map), relationships


def _build_type_relationships(ifc) -> tuple[dict[str, str], list[dict[str, Any]]]:
    """Build occurrence -> type GlobalId relationships."""
    type_map: dict[str, str] = {}
    relationships: list[dict[str, Any]] = []

    for rel in ifc.by_type("IfcRelDefinesByType"):
        type_obj = rel.RelatingType
        type_guid = getattr(type_obj, "GlobalId", None)
        if not type_guid:
            continue

        related = [obj.GlobalId for obj in rel.RelatedObjects if hasattr(obj, "GlobalId")]
        if not related:
            continue

        relationships.append(
            {
                "type_guid": type_guid,
                "type_name": getattr(type_obj, "Name", None),
                "element_guids": related,
            }
        )

        for guid in related:
            type_map[guid] = type_guid

    return type_map, relationships


def _build_property_definition_relationships(ifc) -> list[dict[str, Any]]:
    """Extract IfcRelDefinesByProperties relationships."""
    relationships: list[dict[str, Any]] = []

    for rel in ifc.by_type("IfcRelDefinesByProperties"):
        pset = rel.RelatingPropertyDefinition
        pset_guid = getattr(pset, "GlobalId", None)
        pset_name = getattr(pset, "Name", None)
        related = [obj.GlobalId for obj in rel.RelatedObjects if hasattr(obj, "GlobalId")]
        if related:
            relationships.append(
                {
                    "property_set_guid": pset_guid,
                    "property_set_name": pset_name,
                    "element_guids": related,
                }
            )

    return relationships


def _build_material_map(ifc) -> tuple[dict[str, list[MaterialComponent]], list[dict[str, Any]]]:
    """Extract material associations and flatten to per-element components."""
    material_map: dict[str, list[MaterialComponent]] = defaultdict(list)
    relationships: list[dict[str, Any]] = []

    for rel in ifc.by_type("IfcRelAssociatesMaterial"):
        relating_material = rel.RelatingMaterial
        components = _extract_material_components(relating_material)
        related = [obj.GlobalId for obj in rel.RelatedObjects if hasattr(obj, "GlobalId")]
        if not related:
            continue

        relationships.append(
            {
                "material_type": relating_material.is_a() if relating_material else None,
                "materials": [asdict(component) for component in components],
                "element_guids": related,
            }
        )

        for guid in related:
            existing = {(component.name, component.thickness) for component in material_map[guid]}
            for component in components:
                key = (component.name, component.thickness)
                if key not in existing:
                    material_map[guid].append(component)
                    existing.add(key)

    return dict(material_map), relationships


def _build_classification_map(
    ifc,
) -> tuple[dict[str, list[ClassificationReference]], list[dict[str, Any]]]:
    """Extract classification references from IfcRelAssociatesClassification."""
    classification_map: dict[str, list[ClassificationReference]] = defaultdict(list)
    relationships: list[dict[str, Any]] = []

    for rel in ifc.by_type("IfcRelAssociatesClassification"):
        rc = rel.RelatingClassification
        cref = _extract_classification_reference(rc)
        related = [obj.GlobalId for obj in rel.RelatedObjects if hasattr(obj, "GlobalId")]
        if not related:
            continue

        relationships.append(
            {
                "classification": {
                    "system": cref.system,
                    "reference": cref.reference,
                    "identification": cref.identification,
                },
                "element_guids": related,
            }
        )

        for guid in related:
            exists = {
                (item.system, item.reference, item.identification)
                for item in classification_map[guid]
            }
            key = (cref.system, cref.reference, cref.identification)
            if key not in exists:
                classification_map[guid].append(cref)

    return dict(classification_map), relationships


def _extract_material_components(relating_material) -> list[MaterialComponent]:
    """Flatten IFC material assignment variants into simple components."""
    if relating_material is None:
        return []

    material_type = relating_material.is_a()

    if material_type == "IfcMaterial":
        return [MaterialComponent(name=relating_material.Name or "UnnamedMaterial")]

    if material_type == "IfcMaterialLayerSetUsage":
        layer_set = getattr(relating_material, "ForLayerSet", None)
        return _extract_from_layer_set(layer_set)

    if material_type == "IfcMaterialLayerSet":
        return _extract_from_layer_set(relating_material)

    if material_type == "IfcMaterialConstituentSet":
        components: list[MaterialComponent] = []
        for constituent in getattr(relating_material, "MaterialConstituents", []) or []:
            material = getattr(constituent, "Material", None)
            name = None
            if material and getattr(material, "Name", None):
                name = material.Name
            elif getattr(constituent, "Name", None):
                name = constituent.Name
            if name:
                components.append(MaterialComponent(name=name))
        return components

    if material_type == "IfcMaterialList":
        return [
            MaterialComponent(name=material.Name or "UnnamedMaterial")
            for material in (relating_material.Materials or [])
        ]

    if material_type == "IfcMaterialProfileSetUsage":
        profile_set = getattr(relating_material, "ForProfileSet", None)
        return _extract_from_profile_set(profile_set)

    if material_type == "IfcMaterialProfileSet":
        return _extract_from_profile_set(relating_material)

    name = getattr(relating_material, "Name", None)
    if name:
        return [MaterialComponent(name=name)]
    return []


def _extract_from_layer_set(layer_set) -> list[MaterialComponent]:
    """Extract materials from IfcMaterialLayerSet."""
    if not layer_set:
        return []
    components: list[MaterialComponent] = []
    for layer in getattr(layer_set, "MaterialLayers", []) or []:
        material = getattr(layer, "Material", None)
        name = getattr(material, "Name", None) if material else None
        if not name:
            continue
        thickness = getattr(layer, "LayerThickness", None)
        components.append(MaterialComponent(name=name, thickness=float(thickness) if thickness else None))
    return components


def _extract_from_profile_set(profile_set) -> list[MaterialComponent]:
    """Extract materials from IfcMaterialProfileSet."""
    if not profile_set:
        return []
    components: list[MaterialComponent] = []
    for profile in getattr(profile_set, "MaterialProfiles", []) or []:
        material = getattr(profile, "Material", None)
        name = getattr(material, "Name", None) if material else None
        if name:
            components.append(MaterialComponent(name=name))
    return components


def _extract_classification_reference(relating_classification) -> ClassificationReference:
    """Create a normalized classification reference object."""
    if relating_classification is None:
        return ClassificationReference(system=None, reference=None, identification=None)

    system = None
    reference = None
    identification = None

    if hasattr(relating_classification, "Identification"):
        identification = relating_classification.Identification
    if hasattr(relating_classification, "ItemReference") and not identification:
        identification = relating_classification.ItemReference

    if hasattr(relating_classification, "Name"):
        reference = relating_classification.Name

    if relating_classification.is_a("IfcClassificationReference"):
        referenced_source = getattr(relating_classification, "ReferencedSource", None)
        if referenced_source is not None:
            system = getattr(referenced_source, "Name", None)
    elif relating_classification.is_a("IfcClassification"):
        system = getattr(relating_classification, "Name", None)

    return ClassificationReference(
        system=system,
        reference=reference,
        identification=identification,
    )


def _extract_metadata(ifc) -> dict[str, Any]:
    """Extract file-level metadata from IFC header and entities."""
    header = ifc.header

    metadata: dict[str, Any] = {
        "schema": ifc.schema,
        "timestamp": _first_or_none(header.file_name.time_stamp),
        "author": _first_or_none(header.file_name.author),
        "organization": _first_or_none(header.file_name.organization),
        "originating_system": _first_or_none(header.file_name.originating_system),
        "application": None,
    }

    applications = ifc.by_type("IfcApplication")
    if applications:
        app = applications[-1]
        full = getattr(app, "ApplicationFullName", None)
        version = getattr(app, "Version", None)
        metadata["application"] = " ".join(part for part in (full, version) if part) or None

    if not metadata["author"]:
        persons = ifc.by_type("IfcPerson")
        if persons:
            person = persons[0]
            names = [getattr(person, "GivenName", None), getattr(person, "FamilyName", None)]
            metadata["author"] = " ".join(part for part in names if part) or None

    if not metadata["organization"]:
        organizations = ifc.by_type("IfcOrganization")
        if organizations:
            metadata["organization"] = getattr(organizations[0], "Name", None)

    return metadata


def _first_or_none(value: Any) -> Any:
    """Extract first value from tuple/list fields."""
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return value[0] if value and value[0] else None
    return value


def _extract_attributes(element) -> dict[str, Any]:
    """Extract direct IFC attributes (excluding volatile relationship fields)."""
    skip = {"GlobalId", "OwnerHistory", "ObjectPlacement", "Representation"}
    result: dict[str, Any] = {}

    for idx, value in enumerate(element):
        name = element.attribute_name(idx)
        if name in skip:
            continue
        result[name] = _simplify(value)

    return result


def _extract_psets(element) -> dict[str, dict[str, Any]]:
    """Extract all psets/qtos and strip internal IDs for stable JSON output."""
    psets = ifcopenshell.util.element.get_psets(element)
    cleaned: dict[str, dict[str, Any]] = {}
    for pset_name, props in psets.items():
        if isinstance(props, dict):
            cleaned[pset_name] = {
                key: _simplify(value) for key, value in props.items() if key != "id"
            }
    return cleaned


def _extract_placement(element) -> list[list[float]] | None:
    """Extract 4x4 placement matrix in model coordinates."""
    placement = getattr(element, "ObjectPlacement", None)
    if placement is None:
        return None

    try:
        matrix = ifcopenshell.util.placement.get_local_placement(placement)
        return matrix.tolist()
    except Exception:
        return None


def _extract_type_name(ifc, type_guid: str | None) -> str | None:
    """Resolve type name from a type GlobalId."""
    if not type_guid:
        return None
    try:
        matches = ifc.by_guid(type_guid)
    except Exception:
        return None
    return getattr(matches, "Name", None)


def _extract_owner_history(element) -> dict[str, Any] | None:
    """Extract OwnerHistory fields relevant to audit/change tracking."""
    owner_history = getattr(element, "OwnerHistory", None)
    if owner_history is None:
        return None

    result: dict[str, Any] = {
        "change_action": getattr(owner_history, "ChangeAction", None),
        "created": getattr(owner_history, "CreationDate", None),
        "modified": getattr(owner_history, "LastModifiedDate", None),
    }

    owning_user = getattr(owner_history, "OwningUser", None)
    if owning_user:
        person = getattr(owning_user, "ThePerson", None)
        organization = getattr(owning_user, "TheOrganization", None)
        user_parts = [
            getattr(person, "GivenName", None) if person else None,
            getattr(person, "FamilyName", None) if person else None,
        ]
        result["user"] = " ".join(part for part in user_parts if part) or None
        result["organization"] = getattr(organization, "Name", None) if organization else None

    application = getattr(owner_history, "OwningApplication", None)
    if application:
        parts = [getattr(application, "ApplicationFullName", None), getattr(application, "Version", None)]
        result["application"] = " ".join(part for part in parts if part) or None

    return result


def _extract_geometry_bounds(element) -> dict[str, list[float]] | None:
    """Extract geometry bounds if available; fallback to placement point bounds."""
    placement = _extract_placement(element)

    try:
        import ifcopenshell.geom  # pylint: disable=import-outside-toplevel

        if getattr(element, "Representation", None) is not None:
            settings = ifcopenshell.geom.settings()
            settings.set(settings.USE_WORLD_COORDS, True)
            shape = ifcopenshell.geom.create_shape(settings, element)
            vertices = list(getattr(shape.geometry, "verts", []) or [])
            if vertices:
                xs = vertices[0::3]
                ys = vertices[1::3]
                zs = vertices[2::3]
                return {
                    "min": [min(xs), min(ys), min(zs)],
                    "max": [max(xs), max(ys), max(zs)],
                }
    except Exception:
        pass

    if placement:
        x, y, z = placement[0][3], placement[1][3], placement[2][3]
        return {"min": [x, y, z], "max": [x, y, z]}

    return None


def _strip_revit_trailing_id(name: str | None) -> str | None:
    """Strip trailing numeric ID from Revit-like labels (e.g. Name:12345)."""
    if not name:
        return None
    parts = name.split(":")
    if len(parts) >= 2 and parts[-1].isdigit():
        return ":".join(parts[:-1])
    return name


def _simplify(value: Any) -> Any:
    """Convert IFC attribute values to JSON-serializable scalars/lists/dicts."""
    if value is None:
        return None

    if isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, tuple):
        return [_simplify(item) for item in value]

    if isinstance(value, list):
        return [_simplify(item) for item in value]

    if hasattr(value, "is_a"):
        if hasattr(value, "GlobalId"):
            return {"ref": value.GlobalId, "ifc_class": value.is_a()}
        return {"entity": value.is_a(), "id": value.id()}

    return str(value)


def _entity_to_dict(entity: EntityRecord) -> dict[str, Any]:
    """Convert EntityRecord to dict for compatibility APIs."""
    return {
        "global_id": entity.global_id,
        "ifc_class": entity.ifc_class,
        "name": entity.name,
        "attributes": entity.attributes,
        "property_sets": entity.property_sets,
        "placement": entity.placement,
        "container": entity.spatial_container,
        "type_guid": entity.type_guid,
        "type_name": entity.type_name,
        "owner_history": entity.owner_history,
        "groups": entity.groups,
        "materials": [asdict(material) for material in entity.materials],
        "classifications": [asdict(classification) for classification in entity.classifications],
        "geometry_bounds": entity.geometry_bounds,
    }

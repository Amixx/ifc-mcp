"""Property/classification/type analysis tools."""

from __future__ import annotations

from typing import Any

from ifc_mcp.core.index import ModelIndex


def find_elements_by_property(
    index: ModelIndex,
    property_name: str,
    value: str | None = None,
    operator: str | None = None,
) -> dict[str, Any]:
    """Find elements by property key with equals/contains/exists operators."""
    op = (operator or ("exists" if value is None else "equals")).casefold()
    needle = value.casefold() if isinstance(value, str) else value

    matches: list[dict[str, Any]] = []

    for guid, entity in index.by_guid.items():
        found_values = _find_property_values(entity.property_sets, property_name)
        if _property_match(found_values, op, needle):
            matches.append(
                {
                    "global_id": guid,
                    "ifc_class": entity.ifc_class,
                    "name": entity.name,
                    "values": found_values,
                }
            )

    return {
        "property_name": property_name,
        "operator": op,
        "value": value,
        "count": len(matches),
        "results": matches,
    }


def get_classification(index: ModelIndex, global_id: str) -> dict[str, Any]:
    """Return classification references linked to an element."""
    entity = index.get_entity(global_id)
    if not entity:
        return {"error": f"Element not found: {global_id}"}

    return {
        "global_id": global_id,
        "classifications": [
            {
                "system": cref.system,
                "reference": cref.reference,
                "identification": cref.identification,
            }
            for cref in entity.classifications
        ],
    }


def get_type_info(index: ModelIndex, global_id: str) -> dict[str, Any]:
    """Return type/family information and sibling instances for an element."""
    entity = index.get_entity(global_id)
    if not entity:
        return {"error": f"Element not found: {global_id}"}

    type_guid = entity.type_guid
    if not type_guid and global_id in index.type_map:
        type_guid = global_id

    if not type_guid:
        return {
            "global_id": global_id,
            "type": None,
            "instances": [],
        }

    type_entity = index.get_entity(type_guid)
    instances = [
        index.basic_entity(instance.global_id)
        for instance in index.type_map.get(type_guid, [])
    ]

    return {
        "global_id": global_id,
        "type": {
            "global_id": type_guid,
            "name": type_entity.name if type_entity else entity.type_name,
            "ifc_class": type_entity.ifc_class if type_entity else None,
            "property_sets": type_entity.property_sets if type_entity else {},
        },
        "instances": [instance for instance in instances if instance is not None],
    }


def _find_property_values(property_sets: dict[str, dict[str, Any]], property_name: str) -> list[Any]:
    """Collect all values for matching property name across psets."""
    values = []
    needle = property_name.casefold()
    for _, props in property_sets.items():
        for key, prop_value in props.items():
            if key.casefold() == needle:
                values.append(prop_value)
    return values


def _property_match(values: list[Any], operator: str, value: Any) -> bool:
    """Evaluate values against property match operator."""
    if operator == "exists":
        return bool(values)

    if not values:
        return False

    if operator == "equals":
        for item in values:
            if isinstance(item, str) and isinstance(value, str):
                if item.casefold() == value:
                    return True
            elif item == value:
                return True
        return False

    if operator == "contains":
        if value is None:
            return False
        value_string = str(value).casefold()
        return any(value_string in str(item).casefold() for item in values)

    return False

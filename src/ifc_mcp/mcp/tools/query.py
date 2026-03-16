"""Element query tools."""

from __future__ import annotations

from typing import Any

from ifc_mcp.core.index import ModelIndex


def get_element_by_id(index: ModelIndex, global_id: str) -> dict[str, Any]:
    """Return full details for one element by GlobalId."""
    entity = index.entity_to_dict(global_id)
    if not entity:
        return {"error": f"Element not found: {global_id}"}
    return entity


def search_elements(
    index: ModelIndex,
    ifc_class: str | None = None,
    name: str | None = None,
    floor: str | None = None,
    material: str | None = None,
) -> dict[str, Any]:
    """Search elements with optional AND filters over class/name/floor/material."""
    class_filter = ifc_class.casefold() if ifc_class else None
    name_filter = name.casefold() if name else None
    floor_filter = floor.casefold() if floor else None
    material_filter = material.casefold() if material else None

    results: list[dict[str, Any]] = []

    for guid, entity in index.by_guid.items():
        if class_filter and entity.ifc_class.casefold() != class_filter:
            continue

        scene = index.get_scene(guid)

        if name_filter:
            haystack = f"{entity.name or ''} {scene.label if scene else ''}".casefold()
            if name_filter not in haystack:
                continue

        if floor_filter:
            scene_floor = (scene.floor if scene else None) or ""
            if floor_filter not in scene_floor.casefold():
                continue

        if material_filter:
            materials = [mat.name.casefold() for mat in entity.materials if mat.name]
            if not any(material_filter in mat for mat in materials):
                continue

        basic = index.basic_entity(guid)
        if basic:
            results.append(basic)

    return {"count": len(results), "results": results}


def audit_property_coverage(
    index: ModelIndex,
    property_names: list[str] | None = None,
    requirements: list[dict[str, Any]] | None = None,
    ifc_class: str | None = None,
    name: str | None = None,
    floor: str | None = None,
    material: str | None = None,
    max_examples: int = 20,
) -> dict[str, Any]:
    """Check all matched elements for presence of required properties or aliases."""
    class_filter = ifc_class.casefold() if ifc_class else None
    name_filter = name.casefold() if name else None
    floor_filter = floor.casefold() if floor else None
    material_filter = material.casefold() if material else None
    example_limit = min(max(max_examples, 1), 100)
    effective_requirements = _normalize_requirements(property_names, requirements)

    matched: list[tuple[str, Any, Any]] = []

    for guid, entity in index.by_guid.items():
        if class_filter and entity.ifc_class.casefold() != class_filter:
            continue

        scene = index.get_scene(guid)

        if name_filter:
            haystack = f"{entity.name or ''} {scene.label if scene else ''}".casefold()
            if name_filter not in haystack:
                continue

        if floor_filter:
            scene_floor = (scene.floor if scene else None) or ""
            if floor_filter not in scene_floor.casefold():
                continue

        if material_filter:
            materials = [mat.name.casefold() for mat in entity.materials if mat.name]
            if not any(material_filter in mat for mat in materials):
                continue

        matched.append((guid, entity, scene))

    per_property = {
        requirement["name"]: {
            "property_name": requirement["name"],
            "aliases": requirement["aliases"],
            "present": 0,
            "missing": 0,
            "matched_aliases": {},
        }
        for requirement in effective_requirements
    }
    missing_examples: list[dict[str, Any]] = []

    for guid, entity, scene in matched:
        missing_properties: list[str] = []
        for requirement in effective_requirements:
            match = _find_requirement_match(entity.property_sets, requirement)
            row = per_property[requirement["name"]]
            if match is not None:
                row["present"] += 1
                row["matched_aliases"][match] = row["matched_aliases"].get(match, 0) + 1
            else:
                row["missing"] += 1
                missing_properties.append(requirement["name"])

        if missing_properties and len(missing_examples) < example_limit:
            missing_examples.append(
                {
                    "global_id": guid,
                    "ifc_class": entity.ifc_class,
                    "name": entity.name,
                    "floor": scene.floor if scene else None,
                    "missing_properties": missing_properties,
                }
            )

    total = len(matched)
    property_summary = [
        {
            **row,
            "coverage": round((row["present"] / total), 4) if total else 0.0,
            "matched_aliases": [
                {"alias": alias, "count": row["matched_aliases"][alias]}
                for alias in sorted(row["matched_aliases"])
            ],
        }
        for row in per_property.values()
    ]

    class_counts: dict[str, int] = {}
    for _, entity, _ in matched:
        class_counts[entity.ifc_class] = class_counts.get(entity.ifc_class, 0) + 1

    return {
        "filters": {
            "ifc_class": ifc_class,
            "name": name,
            "floor": floor,
            "material": material,
        },
        "total": total,
        "classes": [{"ifc_class": key, "count": class_counts[key]} for key in sorted(class_counts)],
        "properties": property_summary,
        "all_passing": total > 0 and all(row["missing"] == 0 for row in per_property.values()),
        "missing_examples": missing_examples,
    }


def _normalize_requirements(
    property_names: list[str] | None,
    requirements: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    if requirements:
        normalized = []
        for requirement in requirements:
            name = str(requirement["name"]).strip()
            aliases = []
            for alias in requirement.get("aliases") or []:
                alias_text = str(alias).strip()
                if alias_text and alias_text not in aliases:
                    aliases.append(alias_text)
            normalized.append({"name": name, "aliases": aliases or [name]})
        return normalized
    return [{"name": name, "aliases": [name]} for name in property_names or []]


def _find_requirement_match(property_sets: dict[str, dict[str, Any]], requirement: dict[str, Any]) -> str | None:
    aliases = [alias.casefold() for alias in requirement["aliases"]]
    for props in property_sets.values():
        for key in props:
            if key.casefold() in aliases:
                return key
    return None


def _find_property_values(property_sets: dict[str, dict[str, Any]], property_name: str) -> list[Any]:
    values = []
    needle = property_name.casefold()
    for props in property_sets.values():
        for key, prop_value in props.items():
            if key.casefold() == needle:
                values.append(prop_value)
    return values


def get_element_properties(index: ModelIndex, global_id: str) -> dict[str, Any]:
    """Return all property sets for a specific element."""
    entity = index.get_entity(global_id)
    if not entity:
        return {"error": f"Element not found: {global_id}"}
    return entity.property_sets

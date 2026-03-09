"""Built-in IFC lint rules."""

from __future__ import annotations

from typing import Callable

from ifc_mcp.core.index import ModelIndex, SPATIAL_CLASSES
from ifc_mcp.core.types import LintResult


RULES = {
    "no-unnamed-elements": "Elements without a Name attribute",
    "require-material-assignment": "Elements with no material association",
    "require-spatial-containment": "Elements not assigned to any storey/space",
    "no-empty-property-sets": "Property sets with zero properties",
    "no-duplicate-guids": "Duplicate GlobalIds in the model",
    "no-dead-types": "Type objects with zero instances",
    "require-space-area": "IfcSpaces without area quantity (Qto or Pset)",
    "no-zero-volume-elements": "Elements with zero-volume bounding box",
    "require-classification": "Elements without any classification reference",
}


def no_unnamed_elements(index: ModelIndex) -> list[LintResult]:
    """Flag entities that do not have a populated Name attribute."""
    findings: list[LintResult] = []
    for entity in index.by_guid.values():
        if entity.ifc_class.startswith("IfcType"):
            continue
        if entity.ifc_class in SPATIAL_CLASSES:
            continue
        if not (entity.name or "").strip():
            findings.append(
                LintResult(
                    rule_id="no-unnamed-elements",
                    severity="warn",
                    global_id=entity.global_id,
                    message=f"{entity.ifc_class} has no Name",
                )
            )
    return findings


def require_material_assignment(index: ModelIndex) -> list[LintResult]:
    """Flag entities without any material assignment."""
    findings: list[LintResult] = []
    for entity in index.by_guid.values():
        if entity.ifc_class in SPATIAL_CLASSES:
            continue
        if entity.ifc_class.startswith("IfcType"):
            continue
        if entity.ifc_class in {"IfcOpeningElement", "IfcGroup"}:
            continue
        if not entity.materials:
            findings.append(
                LintResult(
                    rule_id="require-material-assignment",
                    severity="warn",
                    global_id=entity.global_id,
                    message=f"{entity.ifc_class} has no material association",
                )
            )
    return findings


def require_spatial_containment(index: ModelIndex) -> list[LintResult]:
    """Flag elements that are not assigned to a spatial container."""
    findings: list[LintResult] = []
    for entity in index.by_guid.values():
        if entity.ifc_class in SPATIAL_CLASSES:
            continue
        if entity.ifc_class.startswith("IfcType"):
            continue
        if entity.ifc_class in {"IfcGroup"}:
            continue
        if not entity.spatial_container:
            findings.append(
                LintResult(
                    rule_id="require-spatial-containment",
                    severity="warn",
                    global_id=entity.global_id,
                    message=f"{entity.ifc_class} is not assigned to a storey/space",
                )
            )
    return findings


def no_empty_property_sets(index: ModelIndex) -> list[LintResult]:
    """Flag property sets that contain no properties."""
    findings: list[LintResult] = []
    for entity in index.by_guid.values():
        for pset_name, props in entity.property_sets.items():
            if not props:
                findings.append(
                    LintResult(
                        rule_id="no-empty-property-sets",
                        severity="warn",
                        global_id=entity.global_id,
                        message=f"Property set '{pset_name}' is empty",
                    )
                )
    return findings


def no_duplicate_guids(index: ModelIndex) -> list[LintResult]:
    """Flag duplicate GUIDs detected during parsing."""
    return [
        LintResult(
            rule_id="no-duplicate-guids",
            severity="warn",
            global_id=guid,
            message=f"Duplicate GlobalId found: {guid}",
        )
        for guid in index.duplicate_guids
    ]


def no_dead_types(index: ModelIndex) -> list[LintResult]:
    """Flag type objects with no assigned instances."""
    findings: list[LintResult] = []

    for entity in index.by_guid.values():
        if not entity.ifc_class.startswith("Ifc"):
            continue
        if "Type" not in entity.ifc_class:
            continue
        instances = index.type_map.get(entity.global_id, [])
        if not instances:
            findings.append(
                LintResult(
                    rule_id="no-dead-types",
                    severity="warn",
                    global_id=entity.global_id,
                    message=f"{entity.ifc_class} has zero instances",
                )
            )

    return findings


def require_space_area(index: ModelIndex) -> list[LintResult]:
    """Flag spaces missing area quantities."""
    findings: list[LintResult] = []

    for entity in index.by_type.get("IfcSpace", []):
        area = _quantity(entity.property_sets, ["NetArea", "GrossArea", "Area"])
        if area is None:
            findings.append(
                LintResult(
                    rule_id="require-space-area",
                    severity="warn",
                    global_id=entity.global_id,
                    message="IfcSpace has no area quantity in Qto/Pset",
                )
            )

    return findings


def no_zero_volume_elements(index: ModelIndex) -> list[LintResult]:
    """Flag elements with degenerate (zero) volume bounds."""
    findings: list[LintResult] = []

    for entity in index.by_guid.values():
        if entity.ifc_class in SPATIAL_CLASSES:
            continue
        bounds = entity.geometry_bounds
        if not bounds:
            continue
        mins = bounds.get("min")
        maxs = bounds.get("max")
        if not mins or not maxs:
            continue
        volume = (maxs[0] - mins[0]) * (maxs[1] - mins[1]) * (maxs[2] - mins[2])
        if abs(volume) < 1e-9:
            findings.append(
                LintResult(
                    rule_id="no-zero-volume-elements",
                    severity="warn",
                    global_id=entity.global_id,
                    message=f"{entity.ifc_class} has zero-volume geometry bounds",
                )
            )

    return findings


def require_classification(index: ModelIndex) -> list[LintResult]:
    """Flag elements with no classification reference."""
    findings: list[LintResult] = []

    for entity in index.by_guid.values():
        if entity.ifc_class in SPATIAL_CLASSES:
            continue
        if entity.ifc_class.startswith("IfcType"):
            continue
        if not entity.classifications:
            findings.append(
                LintResult(
                    rule_id="require-classification",
                    severity="warn",
                    global_id=entity.global_id,
                    message=f"{entity.ifc_class} has no classification reference",
                )
            )

    return findings


def _quantity(psets: dict[str, dict], keys: list[str]) -> float | None:
    for _, props in psets.items():
        for key in keys:
            value = props.get(key)
            if isinstance(value, (int, float)):
                return float(value)
    return None


RULE_FUNCTIONS: dict[str, Callable[[ModelIndex], list[LintResult]]] = {
    "no-unnamed-elements": no_unnamed_elements,
    "require-material-assignment": require_material_assignment,
    "require-spatial-containment": require_spatial_containment,
    "no-empty-property-sets": no_empty_property_sets,
    "no-duplicate-guids": no_duplicate_guids,
    "no-dead-types": no_dead_types,
    "require-space-area": require_space_area,
    "no-zero-volume-elements": no_zero_volume_elements,
    "require-classification": require_classification,
}

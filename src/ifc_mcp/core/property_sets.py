"""Property set and quantity set traversal helpers.

`ifcopenshell.util.element.get_psets` merges `IfcPropertySet` and
`IfcElementQuantity` into one name-keyed mapping, which loses the distinction
between a real quantity set and a property set that merely looks like one.
These helpers keep that distinction, which QA tooling needs in order to spot
authoring tools that export base quantities into fake property sets.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Literal

PropertySetKind = Literal["pset", "qto", "other"]


@dataclass(frozen=True)
class PropertySetOccurrence:
    """One property/quantity set as it is attached to one element."""

    global_id: str
    ifc_class: str
    set_name: str
    kind: PropertySetKind
    inherited: bool
    property_names: tuple[str, ...]


def iter_property_set_occurrences(
    ifc: Any, entity_type: str = "IfcElement"
) -> Iterator[PropertySetOccurrence]:
    """Yield every property/quantity set attached to every `entity_type` instance.

    Occurrence-level sets (`IfcRelDefinesByProperties`) and type-level sets
    (`IfcTypeObject.HasPropertySets`) are both yielded; type-level ones are
    marked `inherited=True`. Set names are not deduplicated across those two
    sources, so a caller that wants effective presence should fold on
    `(global_id, set_name)` itself.
    """
    for element in ifc.by_type(entity_type):
        yield from element_property_set_occurrences(element)


def element_property_set_occurrences(element: Any) -> list[PropertySetOccurrence]:
    """Return every property/quantity set attached to one element.

    Type-level sets are included and marked `inherited=True`. Callers that need
    a whole model should prefer `iter_property_set_occurrences`.
    """
    global_id = getattr(element, "GlobalId", None)
    if not global_id:
        return []
    ifc_class = element.is_a()
    occurrences = []
    for definition in _occurrence_definitions(element):
        occurrence = _to_occurrence(global_id, ifc_class, definition, inherited=False)
        if occurrence is not None:
            occurrences.append(occurrence)
    for definition in _type_definitions(element):
        occurrence = _to_occurrence(global_id, ifc_class, definition, inherited=True)
        if occurrence is not None:
            occurrences.append(occurrence)
    return occurrences


def _occurrence_definitions(element: Any) -> Iterator[Any]:
    for relation in getattr(element, "IsDefinedBy", None) or []:
        if not relation.is_a("IfcRelDefinesByProperties"):
            continue
        definition = getattr(relation, "RelatingPropertyDefinition", None)
        if definition is None:
            continue
        if definition.is_a("IfcPropertySetDefinitionSet"):
            yield from definition.wrappedValue or []
        elif isinstance(definition, (list, tuple)):
            yield from definition
        else:
            yield definition


def _type_definitions(element: Any) -> Iterator[Any]:
    for element_type in _element_types(element):
        yield from getattr(element_type, "HasPropertySets", None) or []


def _element_types(element: Any) -> Iterator[Any]:
    for relation in getattr(element, "IsTypedBy", None) or []:
        relating_type = getattr(relation, "RelatingType", None)
        if relating_type is not None:
            yield relating_type
    for relation in getattr(element, "IsDefinedBy", None) or []:
        if not relation.is_a("IfcRelDefinesByType"):
            continue
        relating_type = getattr(relation, "RelatingType", None)
        if relating_type is not None:
            yield relating_type


def _to_occurrence(
    global_id: str, ifc_class: str, definition: Any, inherited: bool
) -> PropertySetOccurrence | None:
    set_name = getattr(definition, "Name", None)
    if not set_name:
        return None
    if definition.is_a("IfcElementQuantity"):
        kind: PropertySetKind = "qto"
        members = getattr(definition, "Quantities", None) or []
    elif definition.is_a("IfcPropertySet"):
        kind = "pset"
        members = getattr(definition, "HasProperties", None) or []
    else:
        kind = "other"
        members = []
    names = tuple(
        str(member.Name) for member in members if getattr(member, "Name", None) is not None
    )
    return PropertySetOccurrence(
        global_id=str(global_id),
        ifc_class=ifc_class,
        set_name=str(set_name),
        kind=kind,
        inherited=inherited,
        property_names=names,
    )

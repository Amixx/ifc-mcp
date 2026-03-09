"""Typed data structures used by the IFC core layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


JSONDict = dict[str, Any]


@dataclass(slots=True)
class MaterialComponent:
    """Single material component (layer/constituent/list item)."""

    name: str
    thickness: float | None = None


@dataclass(slots=True)
class ClassificationReference:
    """Classification reference linked to an entity."""

    system: str | None
    reference: str | None
    identification: str | None


@dataclass(slots=True)
class EntityRecord:
    """Normalized IFC entity data keyed by GlobalId."""

    global_id: str
    ifc_class: str
    name: str | None
    attributes: JSONDict = field(default_factory=dict)
    property_sets: dict[str, JSONDict] = field(default_factory=dict)
    placement: list[list[float]] | None = None
    spatial_container: str | None = None
    type_guid: str | None = None
    type_name: str | None = None
    owner_history: JSONDict | None = None
    groups: list[str] = field(default_factory=list)
    materials: list[MaterialComponent] = field(default_factory=list)
    classifications: list[ClassificationReference] = field(default_factory=list)
    geometry_bounds: JSONDict | None = None


@dataclass(slots=True)
class ParsedModel:
    """Full parser output."""

    metadata: JSONDict
    entities: dict[str, EntityRecord]
    relationships: dict[str, list[JSONDict] | dict[str, list[str]]]
    duplicate_guids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SceneElement:
    """Human-oriented scene annotations for an entity."""

    global_id: str
    category: str
    label: str
    floor: str | None
    orientation: str | None
    is_external: bool | None
    host_guid: str | None
    hosted_guids: list[str] = field(default_factory=list)
    parent_guid: str | None = None
    child_guids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SceneModel:
    """Scene model derived from parsed IFC data."""

    elements: dict[str, SceneElement]
    spatial_tree: JSONDict


@dataclass(slots=True)
class LintResult:
    """Single lint finding."""

    rule_id: str
    severity: str
    message: str
    global_id: str | None = None

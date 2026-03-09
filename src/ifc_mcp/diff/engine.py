"""Deterministic IFC diff engine."""

from __future__ import annotations

import json
from typing import Any

from ifc_mcp.core.index import build_index
from ifc_mcp.core.parser import parse_ifc
from ifc_mcp.core.scene import build_scene_model


def diff_ifc_files(old_file: str, new_file: str) -> dict[str, Any]:
    """Compute deterministic basic diff (added/removed/changed entities)."""
    old_parsed = parse_ifc(old_file)
    new_parsed = parse_ifc(new_file)
    old_index = build_index(old_parsed, build_scene_model(old_parsed))
    new_index = build_index(new_parsed, build_scene_model(new_parsed))

    old_ids = set(old_index.by_guid)
    new_ids = set(new_index.by_guid)

    added = sorted(new_ids - old_ids)
    removed = sorted(old_ids - new_ids)
    common = old_ids & new_ids

    changed: list[str] = []
    for guid in sorted(common):
        old_entity = old_index.get_entity(guid)
        new_entity = new_index.get_entity(guid)
        if not old_entity or not new_entity:
            continue
        if _entity_signature(old_entity) != _entity_signature(new_entity):
            changed.append(guid)

    return {
        "old_file": old_file,
        "new_file": new_file,
        "summary": {
            "added": len(added),
            "removed": len(removed),
            "changed": len(changed),
        },
        "added": added,
        "removed": removed,
        "changed": changed,
    }


def _entity_signature(entity) -> tuple[Any, ...]:
    """Create stable tuple signature for lightweight diffing."""
    return (
        entity.ifc_class,
        entity.name,
        entity.spatial_container,
        entity.type_guid,
        json.dumps(entity.property_sets, sort_keys=True, default=str),
        json.dumps(entity.attributes, sort_keys=True, default=str),
        json.dumps(entity.placement, default=str),
    )

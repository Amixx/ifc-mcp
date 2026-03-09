"""Deterministic IFC diff engine."""

from __future__ import annotations

import json
import time
from typing import Any, Callable

from ifc_mcp.core.pipeline import load_model_artifacts


def diff_ifc_files(
    old_file: str,
    new_file: str,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Compute deterministic basic diff (added/removed/changed entities)."""
    old_index = _load_index_with_scope(old_file, "old", progress_callback)
    new_index = _load_index_with_scope(new_file, "new", progress_callback)

    old_ids = set(old_index.by_guid)
    new_ids = set(new_index.by_guid)

    added = sorted(new_ids - old_ids)
    removed = sorted(old_ids - new_ids)
    common = old_ids & new_ids

    compare_started_at = time.monotonic()
    if progress_callback is not None:
        progress_callback(
            {
                "stage": "compare",
                "message": "Comparing shared elements",
                "processed": 0,
                "total": len(common),
                "elapsed_seconds": 0.0,
                "eta_seconds": None,
            }
        )

    changed: list[str] = []
    sorted_common = sorted(common)
    report_every = max(1, len(sorted_common) // 10) if sorted_common else 1
    for idx, guid in enumerate(sorted_common, start=1):
        old_entity = old_index.get_entity(guid)
        new_entity = new_index.get_entity(guid)
        if not old_entity or not new_entity:
            continue
        if _entity_signature(old_entity) != _entity_signature(new_entity):
            changed.append(guid)
        if progress_callback is not None and (idx % report_every == 0 or idx == len(sorted_common)):
            elapsed = time.monotonic() - compare_started_at
            per_item = elapsed / idx if idx else 0.0
            remaining = max(len(sorted_common) - idx, 0)
            progress_callback(
                {
                    "stage": "compare",
                    "message": "Comparing shared elements",
                    "processed": idx,
                    "total": len(sorted_common),
                    "elapsed_seconds": round(elapsed, 2),
                    "eta_seconds": round(per_item * remaining, 2),
                }
            )

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


def _load_index_with_scope(
    file_path: str,
    scope: str,
    progress_callback: Callable[[dict[str, Any]], None] | None,
):
    scoped_callback: Callable[[dict[str, Any]], None] | None = None
    if progress_callback is not None:
        scoped_callback = lambda event: progress_callback({**event, "scope": scope})
    _, _, index = load_model_artifacts(file_path, progress_callback=scoped_callback)
    return index

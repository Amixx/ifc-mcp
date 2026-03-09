"""Model-level metadata and discovery tools."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from ifc_mcp.core.geometry import extract_element_bounds
from ifc_mcp.core.index import ModelIndex


def get_model_summary(index: ModelIndex) -> dict[str, Any]:
    """Get high-level overview of metadata, element counts, floors, spaces, and area."""
    return index.get_summary()


def list_property_sets(index: ModelIndex, ifc_class: str | None = None) -> dict[str, Any]:
    """List all property set names with occurrence counts (optionally filtered by IFC class)."""
    class_filter = ifc_class.casefold() if ifc_class else None
    counts: dict[str, int] = defaultdict(int)

    for entity in index.by_guid.values():
        if class_filter and entity.ifc_class.casefold() != class_filter:
            continue
        for pset_name in entity.property_sets:
            counts[pset_name] += 1

    rows = [
        {"property_set": pset_name, "occurrences": count}
        for pset_name, count in sorted(counts.items())
    ]
    return {"count": len(rows), "property_sets": rows}


def get_element_geometry_bounds(
    index: ModelIndex,
    global_id: str,
    file_path: str | None = None,
) -> dict[str, Any]:
    """Return element bounding box min/max coordinates if available."""
    entity = index.get_entity(global_id)
    if not entity:
        return {"error": f"Element not found: {global_id}"}

    if entity.geometry_bounds:
        return {
            "global_id": global_id,
            "bounds": entity.geometry_bounds,
            "source": "cached",
        }

    effective_path = file_path or index.source_file
    if effective_path:
        bounds = extract_element_bounds(effective_path, global_id)
        if bounds is not None:
            # Cache into active in-memory index so repeated requests are O(1).
            entity.geometry_bounds = bounds
            return {
                "global_id": global_id,
                "bounds": bounds,
                "source": "on_demand",
            }

    return {
        "global_id": global_id,
        "bounds": None,
        "source": "missing",
    }

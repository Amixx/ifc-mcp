"""Model-level metadata and discovery tools."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

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


def get_element_geometry_bounds(index: ModelIndex, global_id: str) -> dict[str, Any]:
    """Return element bounding box min/max coordinates if available."""
    entity = index.get_entity(global_id)
    if not entity:
        return {"error": f"Element not found: {global_id}"}

    return {
        "global_id": global_id,
        "bounds": entity.geometry_bounds,
    }

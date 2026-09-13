"""Building storey helpers."""

from __future__ import annotations

from typing import Any

import ifcopenshell.util.unit


def get_storey_elevations(ifc: Any) -> list[dict[str, Any]]:
    """Return every IfcBuildingStorey with the height the file places it at.

    `elevation_raw` is the `Elevation` attribute as the file states it, in the file's own
    length unit; `elevation_m` and `elevation_mm` are that value converted through the
    project unit scale. All three are unrounded, so a caller deciding how much precision
    a storey height deserves decides it, rather than inheriting a decision made here.

    `Elevation` is optional in IFC and a storey that states none is read as 0.0 — the
    same height the datum sits at — so `elevation_raw` alone does not distinguish an
    unstated elevation from a storey placed at the datum.

    Rows come in the order the file declares the storeys.
    """
    unit_scale = ifcopenshell.util.unit.calculate_unit_scale(ifc)
    rows: list[dict[str, Any]] = []
    for storey in ifc.by_type("IfcBuildingStorey"):
        raw = float(storey.Elevation or 0.0)
        elevation_m = raw * unit_scale
        rows.append(
            {
                "global_id": str(storey.GlobalId),
                "name": storey.Name,
                "elevation_raw": raw,
                "elevation_m": elevation_m,
                "elevation_mm": elevation_m * 1000,
            }
        )
    return rows

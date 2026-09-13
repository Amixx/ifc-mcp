"""Tests for building storey helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import ifcopenshell

from ifc_mcp.core import get_storey_elevations
from ifc_mcp.core import storeys as storeys_module


def test_get_storey_elevations_reports_file_units_metres_and_millimetres(
    monkeypatch: Any,
) -> None:
    _scale(monkeypatch, 0.001)
    ifc = FakeIfc(
        [
            FakeStorey(GlobalId="storey-1", Name="Level 1", Elevation=0.0),
            FakeStorey(GlobalId="storey-2", Name="Level 2", Elevation=3450.0),
        ]
    )

    assert get_storey_elevations(ifc) == [
        {
            "global_id": "storey-1",
            "name": "Level 1",
            "elevation_raw": 0.0,
            "elevation_m": 0.0,
            "elevation_mm": 0.0,
        },
        {
            "global_id": "storey-2",
            "name": "Level 2",
            "elevation_raw": 3450.0,
            "elevation_m": 3.45,
            "elevation_mm": 3450.0,
        },
    ]


def test_get_storey_elevations_keeps_millimetres_unrounded(monkeypatch: Any) -> None:
    _scale(monkeypatch, 0.001)
    ifc = FakeIfc([FakeStorey(GlobalId="storey-1", Name="Level 1", Elevation=2999.6)])

    assert get_storey_elevations(ifc)[0]["elevation_mm"] == 2999.6


def test_get_storey_elevations_reads_an_unstated_elevation_as_the_datum(
    monkeypatch: Any,
) -> None:
    _scale(monkeypatch, 0.001)
    ifc = FakeIfc([FakeStorey(GlobalId="storey-1", Name=None, Elevation=None)])

    [row] = get_storey_elevations(ifc)

    assert (row["name"], row["elevation_raw"], row["elevation_m"]) == (None, 0.0, 0.0)


def test_get_storey_elevations_keeps_declaration_order(monkeypatch: Any) -> None:
    _scale(monkeypatch, 0.001)
    ifc = FakeIfc(
        [
            FakeStorey(GlobalId="storey-high", Name="Roof", Elevation=9000.0),
            FakeStorey(GlobalId="storey-low", Name="Ground", Elevation=0.0),
        ]
    )

    assert [row["global_id"] for row in get_storey_elevations(ifc)] == [
        "storey-high",
        "storey-low",
    ]


def test_get_storey_elevations_converts_a_metre_file(monkeypatch: Any) -> None:
    _scale(monkeypatch, 1.0)
    ifc = FakeIfc([FakeStorey(GlobalId="storey-1", Name="Level 1", Elevation=3.45)])

    [row] = get_storey_elevations(ifc)

    assert (row["elevation_raw"], row["elevation_m"], row["elevation_mm"]) == (
        3.45,
        3.45,
        3450.0,
    )


def test_get_storey_elevations_reads_a_real_model(residential_ifc: Any) -> None:
    rows = get_storey_elevations(ifcopenshell.open(str(residential_ifc)))

    assert rows == [
        {
            "global_id": "1Ano2ZUxnEIvVQ_beukl8b",
            "name": "00 groundfloor",
            "elevation_raw": -1.8047785488306545e-12,
            "elevation_m": -1.8047785488306545e-15,
            "elevation_mm": -1.8047785488306545e-12,
        }
    ]


def _scale(monkeypatch: Any, unit_scale: float) -> None:
    monkeypatch.setattr(
        storeys_module.ifcopenshell.util.unit,
        "calculate_unit_scale",
        lambda _ifc: unit_scale,
    )


@dataclass
class FakeStorey:
    GlobalId: str
    Name: str | None
    Elevation: float | None


@dataclass
class FakeIfc:
    storeys: list[FakeStorey]

    def by_type(self, class_name: str) -> list[Any]:
        return list(self.storeys) if class_name == "IfcBuildingStorey" else []

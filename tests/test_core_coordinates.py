"""Tests for site placement helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import ifcopenshell

from ifc_mcp.core import coordinates as coordinates_module
from ifc_mcp.core import get_site_coordinates


def test_get_site_coordinates_reports_file_units_and_metres(monkeypatch: Any) -> None:
    _place_site(monkeypatch, (12000.0, -3500.0, 250.0))
    ifc = FakeIfc(sites=[FakeSite(GlobalId="site-1", Name="Plot 4")])

    coordinates = get_site_coordinates(ifc)

    assert coordinates is not None
    assert coordinates["global_id"] == "site-1"
    assert coordinates["name"] == "Plot 4"
    assert coordinates["unit_scale_to_m"] == 0.001
    assert (coordinates["x_raw"], coordinates["y_raw"], coordinates["z_raw"]) == (
        12000.0,
        -3500.0,
        250.0,
    )
    assert (coordinates["x_m"], coordinates["y_m"], coordinates["z_m"]) == (
        12.0,
        -3.5,
        0.25,
    )
    assert (coordinates["x_mm"], coordinates["y_mm"], coordinates["z_mm"]) == (
        12000.0,
        -3500.0,
        250.0,
    )


def test_get_site_coordinates_returns_none_without_a_site() -> None:
    assert get_site_coordinates(FakeIfc(sites=[])) is None


def test_get_site_coordinates_reads_the_first_site_the_file_declares(
    monkeypatch: Any,
) -> None:
    _place_site(monkeypatch, (1.0, 0.0, 0.0))
    ifc = FakeIfc(sites=[FakeSite(GlobalId="site-1"), FakeSite(GlobalId="site-2")])

    coordinates = get_site_coordinates(ifc)

    assert coordinates is not None and coordinates["global_id"] == "site-1"


def test_get_site_coordinates_measures_rotation_counterclockwise_from_x(
    monkeypatch: Any,
) -> None:
    monkeypatch.setattr(
        coordinates_module.ifcopenshell.util.unit,
        "calculate_unit_scale",
        lambda _ifc: 1.0,
    )
    monkeypatch.setattr(
        coordinates_module.ifcopenshell.util.placement,
        "get_local_placement",
        lambda _placement: [
            [0.0, -1.0, 0.0, 0.0],
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ],
    )
    ifc = FakeIfc(sites=[FakeSite(GlobalId="site-1")])

    coordinates = get_site_coordinates(ifc)

    assert coordinates is not None and coordinates["rotation_deg"] == 90.0


def test_get_site_coordinates_reads_true_north_clockwise_from_y(
    monkeypatch: Any,
) -> None:
    _place_site(monkeypatch, (0.0, 0.0, 0.0))
    ifc = FakeIfc(
        sites=[FakeSite(GlobalId="site-1")],
        contexts=[FakeContext(FakeDirection((1.0, 1.0)))],
    )

    coordinates = get_site_coordinates(ifc)

    assert coordinates is not None and coordinates["true_north_deg"] == 45.0


def test_get_site_coordinates_skips_a_context_pointing_nowhere(
    monkeypatch: Any,
) -> None:
    """A zero direction and a single ratio name no direction in the XY plane."""
    _place_site(monkeypatch, (0.0, 0.0, 0.0))
    ifc = FakeIfc(
        sites=[FakeSite(GlobalId="site-1")],
        contexts=[
            FakeContext(None),
            FakeContext(FakeDirection((0.0, 0.0))),
            FakeContext(FakeDirection((1.0,))),
            FakeContext(FakeDirection((-1.0, 0.0))),
        ],
    )

    coordinates = get_site_coordinates(ifc)

    assert coordinates is not None and coordinates["true_north_deg"] == -90.0


def test_get_site_coordinates_leaves_true_north_unstated(monkeypatch: Any) -> None:
    _place_site(monkeypatch, (0.0, 0.0, 0.0))
    ifc = FakeIfc(sites=[FakeSite(GlobalId="site-1")], contexts=[FakeContext(None)])

    coordinates = get_site_coordinates(ifc)

    assert coordinates is not None and coordinates["true_north_deg"] is None


def test_get_site_coordinates_reads_a_real_model(residential_ifc: Any) -> None:
    coordinates = get_site_coordinates(ifcopenshell.open(str(residential_ifc)))

    assert coordinates == {
        "global_id": "23sFQGRy90RxVbRHD9iSE2",
        "name": "environment - site",
        "unit_scale_to_m": 0.001,
        "x_raw": 0.0,
        "y_raw": 0.0,
        "z_raw": 0.0,
        "x_m": 0.0,
        "y_m": 0.0,
        "z_m": 0.0,
        "x_mm": 0.0,
        "y_mm": 0.0,
        "z_mm": 0.0,
        "rotation_deg": 0.0,
        "true_north_deg": 0.0,
    }


def _place_site(monkeypatch: Any, translation: tuple[float, float, float]) -> None:
    x, y, z = translation
    monkeypatch.setattr(
        coordinates_module.ifcopenshell.util.unit,
        "calculate_unit_scale",
        lambda _ifc: 0.001,
    )
    monkeypatch.setattr(
        coordinates_module.ifcopenshell.util.placement,
        "get_local_placement",
        lambda _placement: [
            [1.0, 0.0, 0.0, x],
            [0.0, 1.0, 0.0, y],
            [0.0, 0.0, 1.0, z],
            [0.0, 0.0, 0.0, 1.0],
        ],
    )


@dataclass
class FakeDirection:
    DirectionRatios: tuple[float, ...]


@dataclass
class FakeContext:
    TrueNorth: FakeDirection | None


@dataclass
class FakeSite:
    GlobalId: str
    Name: str | None = None
    ObjectPlacement: Any = None


@dataclass
class FakeIfc:
    sites: list[FakeSite]
    contexts: list[FakeContext] = field(default_factory=list)

    def by_type(self, class_name: str) -> list[Any]:
        if class_name == "IfcSite":
            return list(self.sites)
        if class_name == "IfcGeometricRepresentationContext":
            return list(self.contexts)
        return []

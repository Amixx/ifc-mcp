"""Tests for grid geometry helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import ifcopenshell

from ifc_mcp.core import get_grid_axis_tags, get_grid_extents
from ifc_mcp.core import grids as grid_module


def test_get_grid_extents_transforms_polyline_points(monkeypatch: Any) -> None:
    monkeypatch.setattr(grid_module.ifcopenshell.util.unit, "calculate_unit_scale", lambda _ifc: 0.001)
    monkeypatch.setattr(
        grid_module.ifcopenshell.util.placement,
        "get_local_placement",
        lambda _placement: [
            [1.0, 0.0, 0.0, 2.0],
            [0.0, 1.0, 0.0, -1.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ],
    )
    ifc = FakeIfc(
        [
            FakeGrid(
                GlobalId="grid-b",
                UAxes=[
                    FakeAxis(FakePolyline([FakePoint((0.0, 0.0)), FakePoint((10.0, 5.0))]))
                ],
                VAxes=[FakeAxis(FakePolyline([FakePoint((-4.0, 8.0, 2.0))]))],
            ),
            FakeGrid(
                GlobalId="grid-a",
                UAxes=[FakeAxis(FakeCurve())],
            ),
        ]
    )

    assert get_grid_extents(ifc) == {
        "grid_global_ids": ["grid-b"],
        "axis_count": 2,
        "min_x_m": -0.002,
        "max_x_m": 0.012,
        "min_y_m": -0.001,
        "max_y_m": 0.007,
    }


def test_get_grid_extents_returns_none_without_grids() -> None:
    ifc = ifcopenshell.open("data/BasicHouse.ifc")

    assert get_grid_extents(ifc) is None


def test_get_grid_axis_tags_reads_every_axis_list() -> None:
    ifc = FakeIfc(
        [
            FakeGrid(
                GlobalId="grid-b",
                UAxes=[FakeAxis(FakeCurve(), AxisTag="A"), FakeAxis(FakeCurve(), AxisTag="B")],
                VAxes=[FakeAxis(FakeCurve(), AxisTag="1")],
                WAxes=[FakeAxis(FakeCurve(), AxisTag="Z")],
            ),
            FakeGrid(GlobalId="grid-a"),
        ]
    )

    assert get_grid_axis_tags(ifc) == [
        {"global_id": "grid-a", "axis_tags": []},
        {"global_id": "grid-b", "axis_tags": ["A", "B", "1", "Z"]},
    ]


def test_get_grid_axis_tags_keeps_an_untagged_axis_distinguishable() -> None:
    ifc = FakeIfc(
        [
            FakeGrid(
                GlobalId="grid-a",
                UAxes=[FakeAxis(FakeCurve(), AxisTag="A"), FakeAxis(FakeCurve())],
            )
        ]
    )

    assert get_grid_axis_tags(ifc) == [{"global_id": "grid-a", "axis_tags": ["A", None]}]


@dataclass
class FakePoint:
    Coordinates: tuple[float, ...]


@dataclass
class FakeCurve:
    def is_a(self, class_name: str) -> bool:
        return class_name == "IfcCurve"


@dataclass
class FakePolyline:
    Points: list[FakePoint]

    def is_a(self, class_name: str) -> bool:
        return class_name == "IfcPolyline"


@dataclass
class FakeAxis:
    AxisCurve: FakeCurve | FakePolyline
    AxisTag: str | None = None


@dataclass
class FakeGrid:
    GlobalId: str
    UAxes: list[FakeAxis] | None = None
    VAxes: list[FakeAxis] | None = None
    WAxes: list[FakeAxis] | None = None
    ObjectPlacement: object | None = None


@dataclass
class FakeIfc:
    grids: list[FakeGrid]

    def by_type(self, class_name: str) -> list[FakeGrid]:
        return self.grids if class_name == "IfcGrid" else []

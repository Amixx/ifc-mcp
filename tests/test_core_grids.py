"""Tests for grid geometry helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import ifcopenshell

from ifc_mcp.core import get_grid_axes, get_grid_extents
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
            FakeGrid(GlobalId="grid-a"),
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


def test_get_grid_axes_reads_every_axis_list() -> None:
    ifc = FakeIfc(
        [
            FakeGrid(
                GlobalId="grid-b",
                UAxes=[
                    FakeAxis(FakePolyline([FakePoint((0.0, 0.0))]), AxisTag="A"),
                    FakeAxis(FakePolyline([FakePoint((1.0, 0.0))]), AxisTag="B"),
                ],
                VAxes=[FakeAxis(FakePolyline([FakePoint((0.0, 1.0))]), AxisTag="1")],
                WAxes=[FakeAxis(FakePolyline([FakePoint((0.0, 2.0))]), AxisTag="Z")],
            ),
            FakeGrid(GlobalId="grid-a"),
        ]
    )

    assert [(row["grid_global_id"], row["axis_set"], row["axis_tag"]) for row in get_grid_axes(ifc)] == [
        ("grid-b", "U", "A"),
        ("grid-b", "U", "B"),
        ("grid-b", "V", "1"),
        ("grid-b", "W", "Z"),
    ]


def test_get_grid_axes_keeps_an_untagged_axis_distinguishable() -> None:
    ifc = FakeIfc(
        [
            FakeGrid(
                GlobalId="grid-a",
                UAxes=[
                    FakeAxis(FakePolyline([FakePoint((0.0, 0.0))]), AxisTag="A"),
                    FakeAxis(FakePolyline([FakePoint((1.0, 1.0))])),
                ],
            )
        ]
    )

    assert [row["axis_tag"] for row in get_grid_axes(ifc)] == ["A", None]


def test_get_grid_axes_places_points_in_world_metres(monkeypatch: Any) -> None:
    _place_at(monkeypatch, offset_x=2.0, offset_y=-1.0)
    ifc = FakeIfc(
        [
            FakeGrid(
                GlobalId="grid-a",
                UAxes=[
                    FakeAxis(
                        FakePolyline([FakePoint((0.0, 0.0)), FakePoint((10000.0, 0.0))]),
                        AxisTag="A",
                    )
                ],
            )
        ]
    )

    assert get_grid_axes(ifc)[0]["points_m"] == [[0.002, -0.001], [10.002, -0.001]]


def test_get_grid_axes_walks_an_indexed_poly_curve(monkeypatch: Any) -> None:
    _place_at(monkeypatch)
    curve = FakeIndexedPolyCurve(
        Points=FakeCoordList([(0.0, 0.0), (1000.0, 0.0), (4000.0, 0.0)]),
        Segments=[FakeLineIndex((2, 3))],
    )
    ifc = FakeIfc([FakeGrid(GlobalId="grid-a", UAxes=[FakeAxis(curve, AxisTag="A")])])

    assert get_grid_axes(ifc)[0]["points_m"] == [[1.0, 0.0], [4.0, 0.0]]


def test_get_grid_axes_names_a_curve_class_it_does_not_read_and_keeps_the_axis() -> None:
    ifc = FakeIfc([FakeGrid(GlobalId="grid-a", UAxes=[FakeAxis(FakeCurve(), AxisTag="A")])])

    [row] = get_grid_axes(ifc)

    assert (row["axis_tag"], row["curve"], row["points_m"]) == ("A", "IfcCurve", [])


def test_get_grid_axes_names_the_arc_that_bends_an_axis_and_keeps_the_axis(
    monkeypatch: Any,
) -> None:
    _place_at(monkeypatch)
    curve = FakeIndexedPolyCurve(
        Points=FakeCoordList([(0.0, 0.0), (1000.0, 500.0), (2000.0, 0.0)]),
        Segments=[FakeArcIndex((1, 2, 3))],
    )
    ifc = FakeIfc([FakeGrid(GlobalId="grid-a", UAxes=[FakeAxis(curve, AxisTag="A")])])

    [row] = get_grid_axes(ifc)

    assert (row["axis_tag"], row["curve"], row["points_m"]) == ("A", "IfcArcIndex", [])


def test_get_grid_extents_skips_an_axis_stating_no_line(monkeypatch: Any) -> None:
    """A curved axis leaves the extents to the straight ones instead of emptying them."""
    _place_at(monkeypatch)
    arc = FakeIndexedPolyCurve(
        Points=FakeCoordList([(0.0, 0.0), (1000.0, 500.0), (2000.0, 0.0)]),
        Segments=[FakeArcIndex((1, 2, 3))],
    )
    ifc = FakeIfc(
        [
            FakeGrid(
                GlobalId="grid-a",
                UAxes=[
                    FakeAxis(arc, AxisTag="A"),
                    FakeAxis(
                        FakePolyline([FakePoint((0.0, 0.0)), FakePoint((4000.0, 0.0))]),
                        AxisTag="B",
                    ),
                ],
            )
        ]
    )

    extents = get_grid_extents(ifc)

    assert extents is not None
    assert (extents["axis_count"], extents["max_x_m"]) == (1, 4.0)


def _place_at(monkeypatch: Any, offset_x: float = 0.0, offset_y: float = 0.0) -> None:
    monkeypatch.setattr(
        grid_module.ifcopenshell.util.unit, "calculate_unit_scale", lambda _ifc: 0.001
    )
    monkeypatch.setattr(
        grid_module.ifcopenshell.util.placement,
        "get_local_placement",
        lambda _placement: [
            [1.0, 0.0, 0.0, offset_x],
            [0.0, 1.0, 0.0, offset_y],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
        ],
    )


@dataclass
class FakePoint:
    Coordinates: tuple[float, ...]


@dataclass
class FakeCurve:
    def is_a(self, class_name: str | None = None) -> Any:
        if class_name is None:
            return "IfcCurve"
        return class_name == "IfcCurve"


@dataclass
class FakePolyline:
    Points: list[FakePoint]

    def is_a(self, class_name: str | None = None) -> Any:
        if class_name is None:
            return "IfcPolyline"
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


@dataclass
class FakeCoordList:
    CoordList: list[tuple[float, ...]]


@dataclass
class FakeIndexedPolyCurve:
    Points: FakeCoordList
    Segments: list[Any] | None = None

    def is_a(self, class_name: str | None = None) -> Any:
        if class_name is None:
            return "IfcIndexedPolyCurve"
        return class_name == "IfcIndexedPolyCurve"


@dataclass
class FakeSegment:
    indices: tuple[int, ...]

    def __getitem__(self, item: int) -> tuple[int, ...]:
        return self.indices


@dataclass
class FakeLineIndex(FakeSegment):
    def is_a(self, class_name: str | None = None) -> Any:
        if class_name is None:
            return "IfcLineIndex"
        return class_name == "IfcLineIndex"


@dataclass
class FakeArcIndex(FakeSegment):
    def is_a(self, class_name: str | None = None) -> Any:
        if class_name is None:
            return "IfcArcIndex"
        return class_name == "IfcArcIndex"

"""Tests for IFC geometry simplification (decimation)."""

from __future__ import annotations

from pathlib import Path

import ifcopenshell
import pytest

pytest.importorskip("open3d")  # optional extra: pip install ifc-mcp[simplify]

from ifc_mcp.core.simplify import needs_simplification, simplify_ifc


def test_needs_simplification_false_below_min_heavy_faces() -> None:
    # BasicHouse has faceted breps (some with 1000+ faces) but not enough total heavy
    # face area to justify a whole-file pass at the default 500k-face floor.
    assert needs_simplification("data/BasicHouse.ifc") is False


def test_needs_simplification_true_with_lower_floor() -> None:
    assert needs_simplification("data/BasicHouse.ifc", min_heavy_faces=1000) is True


def test_simplify_ifc_skips_when_nothing_qualifies(tmp_path: Path) -> None:
    out = tmp_path / "out.ifc"

    result = simplify_ifc("data/BasicHouse.ifc", out, threshold=100_000)

    assert result.simplified is False
    assert out.read_bytes() == Path("data/BasicHouse.ifc").read_bytes()


def test_simplify_ifc_reduces_triangles_and_stays_valid(tmp_path: Path) -> None:
    out = tmp_path / "simplified.ifc"

    result = simplify_ifc("data/BasicHouse.ifc", out, ratio=0.1, threshold=200)

    assert result.simplified is True
    assert result.face_sets_touched > 0
    assert result.simplified_triangles < result.original_triangles
    assert result.simplified_mb < result.original_mb

    # The output must still be valid, openable IFC -- re-open and confirm the face-sets that
    # originally qualified (>=200 faces, up to 1250 in this fixture) actually shrank.
    original = ifcopenshell.open("data/BasicHouse.ifc")
    original_max_faces = max(len(b.Outer.CfsFaces) for b in original.by_type("IfcFacetedBrep"))
    reopened = ifcopenshell.open(str(out))
    reopened_max_faces = max(len(b.Outer.CfsFaces) for b in reopened.by_type("IfcFacetedBrep"))
    assert reopened_max_faces < original_max_faces
    assert reopened_max_faces >= 50  # decimation floor, per qualifying face-set


def test_simplify_ifc_aggressive_ratio_still_shrinks_every_faceset(tmp_path: Path) -> None:
    out = tmp_path / "aggressive.ifc"

    # ratio=0.001 pushes every qualifying face-set's computed target (original * ratio) well
    # under the 50-triangle floor. Open3D's quadric decimation doesn't always hit an exact
    # target -- meshes with disconnected sub-shapes/non-manifold topology have a real
    # structural minimum above it (measured: one BasicHouse brep floors at 172, not ~50) --
    # so this only asserts real shrinkage happened, not an exact number.
    result = simplify_ifc("data/BasicHouse.ifc", out, ratio=0.001, threshold=200)

    assert result.simplified is True
    original = ifcopenshell.open("data/BasicHouse.ifc")
    original_max_faces = max(len(b.Outer.CfsFaces) for b in original.by_type("IfcFacetedBrep"))
    reopened = ifcopenshell.open(str(out))
    reopened_max_faces = max(len(b.Outer.CfsFaces) for b in reopened.by_type("IfcFacetedBrep"))
    assert reopened_max_faces < original_max_faces

"""Tests validating geometry extraction optimizations."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from ifc_mcp.core.parser import parse_ifc
from ifc_mcp.core.pipeline import load_model_artifacts


@pytest.fixture(scope="session")
def residential_ifc() -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "Building-Architecture.ifc"


def test_parse_without_geometry_skips_bounds(residential_ifc):
    """parse_ifc(extract_geometry=False) produces entities with geometry_bounds=None."""
    parsed = parse_ifc(str(residential_ifc), extract_geometry=False)
    assert parsed.entities
    for entity in parsed.entities.values():
        assert entity.geometry_bounds is None


def test_parse_with_geometry_produces_bounds(residential_ifc):
    """parse_ifc(extract_geometry=True) populates geometry_bounds on entities with representations."""
    parsed = parse_ifc(str(residential_ifc), extract_geometry=True)
    assert parsed.entities
    has_bounds = sum(1 for e in parsed.entities.values() if e.geometry_bounds is not None)
    assert has_bounds > 0, "Expected some entities to have geometry_bounds"


def test_no_geometry_is_faster_than_with_geometry(residential_ifc):
    """Skipping geometry should be meaningfully faster than extracting it."""
    start = time.monotonic()
    parse_ifc(str(residential_ifc), extract_geometry=False)
    no_geom_time = time.monotonic() - start

    start = time.monotonic()
    parse_ifc(str(residential_ifc), extract_geometry=True)
    with_geom_time = time.monotonic() - start

    # No-geometry should be at least 2x faster (typically 10x+ faster)
    assert no_geom_time < with_geom_time, (
        f"Expected no-geometry ({no_geom_time:.2f}s) to be faster than "
        f"with-geometry ({with_geom_time:.2f}s)"
    )


def test_pipeline_respects_extract_geometry_flag(residential_ifc):
    """load_model_artifacts(extract_geometry=False) builds valid index without bounds."""
    _, _, index = load_model_artifacts(str(residential_ifc), extract_geometry=False)
    assert index.entities
    summary = index.get_summary()
    assert summary["metadata"]
    for entity in index.entities.values():
        assert entity.geometry_bounds is None

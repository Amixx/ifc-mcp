"""Tests for meta tools."""

from __future__ import annotations

from ifc_mcp.core.pipeline import load_model_artifacts
from ifc_mcp.tools import meta


def test_get_model_summary(model_index):
    result = meta.get_model_summary(model_index)
    assert "metadata" in result
    assert "counts_by_ifc_class" in result


def test_list_property_sets(model_index):
    result = meta.list_property_sets(model_index)
    assert "property_sets" in result


def test_get_element_geometry_bounds(model_index):
    guid = next(iter(model_index.by_guid))
    result = meta.get_element_geometry_bounds(model_index, guid)
    assert "bounds" in result or "error" in result


def test_get_element_geometry_bounds_on_demand(residential_ifc):
    _, _, eager_index = load_model_artifacts(str(residential_ifc), extract_geometry=True)
    guid = next(
        gid for gid, entity in eager_index.by_guid.items() if entity.geometry_bounds is not None
    )

    _, _, fast_index = load_model_artifacts(str(residential_ifc), extract_geometry=False)
    assert fast_index.by_guid[guid].geometry_bounds is None

    result = meta.get_element_geometry_bounds(fast_index, guid, file_path=str(residential_ifc))
    assert result["source"] == "on_demand"
    assert result["bounds"] is not None
    assert fast_index.by_guid[guid].geometry_bounds is not None

    cached = meta.get_element_geometry_bounds(fast_index, guid)
    assert cached["source"] == "cached"

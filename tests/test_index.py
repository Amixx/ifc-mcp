"""Tests for model index lookups."""

from __future__ import annotations


def test_index_has_guid_lookup(model_index):
    assert model_index.by_guid
    guid = next(iter(model_index.by_guid))
    assert model_index.get_entity(guid) is not None


def test_index_has_groupings(model_index):
    assert isinstance(model_index.by_type, dict)
    assert isinstance(model_index.by_floor, dict)
    assert isinstance(model_index.by_material, dict)


def test_index_summary_shape(model_index):
    summary = model_index.get_summary()
    assert "metadata" in summary
    assert "counts_by_ifc_class" in summary
    assert "floor_count" in summary
    assert "total_spaces" in summary

"""Tests for scene model builder."""

from __future__ import annotations


def test_build_scene_model_has_elements(scene_model):
    assert scene_model.elements
    assert len(scene_model.elements) > 0


def test_scene_labels_are_human_readable(scene_model):
    sample = next(iter(scene_model.elements.values()))
    assert isinstance(sample.label, str)
    assert sample.label != ""


def test_scene_has_spatial_tree(scene_model):
    assert "roots" in scene_model.spatial_tree
    assert isinstance(scene_model.spatial_tree["roots"], list)

"""Tests for IFC parser output."""

from __future__ import annotations


def test_parse_ifc_extracts_metadata_and_entities(parsed_model):
    assert parsed_model.metadata.get("schema")
    assert parsed_model.entities
    assert len(parsed_model.entities) > 0


def test_parse_ifc_relationship_sections_present(parsed_model):
    keys = set(parsed_model.relationships.keys())
    expected = {
        "voids",
        "fills",
        "aggregates",
        "spatial_containment",
        "assigns_to_group",
        "associates_material",
        "defines_by_type",
        "defines_by_properties",
    }
    assert expected.issubset(keys)


def test_parse_ifc_entity_fields_are_populated(parsed_model):
    guid, entity = next(iter(parsed_model.entities.items()))
    assert guid == entity.global_id
    assert entity.ifc_class.startswith("Ifc")
    assert isinstance(entity.attributes, dict)
    assert isinstance(entity.property_sets, dict)

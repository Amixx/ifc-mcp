"""Tests for IFC parser output."""

from __future__ import annotations

from ifc_mcp.core.parser import _extract_classification_reference


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


class _StubClassification:
    """The subset of an ifcopenshell classification entity the extractor reads."""

    def __init__(self, ifc_class, express_id, name=None, identification=None, source=None):
        self._ifc_class = ifc_class
        self._express_id = express_id
        self.Name = name
        self.Identification = identification
        self.ReferencedSource = source

    def is_a(self, ifc_class=None):
        return self._ifc_class if ifc_class is None else self._ifc_class == ifc_class

    def id(self):
        return self._express_id


def test_classification_system_resolves_through_a_nested_reference_chain():
    """Uniclass and OmniClass tables export as facets nested under the classification."""
    table = _StubClassification("IfcClassification", 1, name="Uniclass 2015")
    facet = _StubClassification(
        "IfcClassificationReference", 2, name="Systems", identification="Ss", source=table
    )
    leaf = _StubClassification(
        "IfcClassificationReference",
        3,
        name="Concrete framed structures",
        identification="Ss_20_10_30",
        source=facet,
    )

    reference = _extract_classification_reference(leaf)

    assert reference.system == "Uniclass 2015"
    assert reference.reference == "Concrete framed structures"
    assert reference.identification == "Ss_20_10_30"


def test_classification_association_against_a_table_names_only_the_system():
    table = _StubClassification("IfcClassification", 1, name="Uniclass 2015")

    reference = _extract_classification_reference(table)

    assert reference.system == "Uniclass 2015"
    assert reference.reference is None
    assert reference.identification is None


def test_classification_reference_chain_survives_a_cycle():
    first = _StubClassification("IfcClassificationReference", 1, name="A")
    second = _StubClassification("IfcClassificationReference", 2, name="B", source=first)
    first.ReferencedSource = second

    assert _extract_classification_reference(second).system is None

"""Tests for property set / quantity set traversal helpers."""

from __future__ import annotations

import ifcopenshell

from ifc_mcp.core import element_property_set_occurrences, iter_property_set_occurrences


def _build_model() -> ifcopenshell.file:
    ifc = ifcopenshell.file(schema="IFC4")
    owner = None

    covering_type = ifc.create_entity("IfcCoveringType", GlobalId="0type000000000000000000")
    covering = ifc.create_entity("IfcCovering", GlobalId="0cov0000000000000000000")
    duct = ifc.create_entity("IfcDuctSegment", GlobalId="0duct000000000000000000")

    fake_qto = ifc.create_entity(
        "IfcPropertySet",
        GlobalId="0fake000000000000000000",
        Name="XQto_CoveringBaseQuantities",
        HasProperties=[
            ifc.create_entity(
                "IfcPropertySingleValue",
                Name="GrossArea",
                NominalValue=ifc.create_entity("IfcAreaMeasure", 1.5),
            )
        ],
    )
    real_qto = ifc.create_entity(
        "IfcElementQuantity",
        GlobalId="0real000000000000000000",
        Name="Qto_DuctSegmentBaseQuantities",
        Quantities=[ifc.create_entity("IfcQuantityLength", Name="Length", LengthValue=2.0)],
    )
    type_pset = ifc.create_entity(
        "IfcPropertySet",
        GlobalId="0tset000000000000000000",
        Name="VAMOIC",
        HasProperties=[
            ifc.create_entity(
                "IfcPropertySingleValue",
                Name="Nosaukums",
                NominalValue=ifc.create_entity("IfcText", "Griestu apdare"),
            )
        ],
    )
    covering_type.HasPropertySets = [type_pset]

    ifc.create_entity(
        "IfcRelDefinesByProperties",
        GlobalId="0rel1000000000000000000",
        OwnerHistory=owner,
        RelatedObjects=[covering],
        RelatingPropertyDefinition=fake_qto,
    )
    ifc.create_entity(
        "IfcRelDefinesByProperties",
        GlobalId="0rel2000000000000000000",
        OwnerHistory=owner,
        RelatedObjects=[duct],
        RelatingPropertyDefinition=real_qto,
    )
    ifc.create_entity(
        "IfcRelDefinesByType",
        GlobalId="0rel3000000000000000000",
        OwnerHistory=owner,
        RelatedObjects=[covering],
        RelatingType=covering_type,
    )
    return ifc


def test_iter_property_set_occurrences_separates_psets_from_quantity_sets() -> None:
    occurrences = list(iter_property_set_occurrences(_build_model()))
    by_name = {occurrence.set_name: occurrence for occurrence in occurrences}

    assert by_name["XQto_CoveringBaseQuantities"].kind == "pset"
    assert by_name["XQto_CoveringBaseQuantities"].ifc_class == "IfcCovering"
    assert by_name["XQto_CoveringBaseQuantities"].property_names == ("GrossArea",)
    assert by_name["Qto_DuctSegmentBaseQuantities"].kind == "qto"
    assert by_name["Qto_DuctSegmentBaseQuantities"].property_names == ("Length",)


def test_iter_property_set_occurrences_marks_type_sets_as_inherited() -> None:
    occurrences = list(iter_property_set_occurrences(_build_model()))
    vamoic = [occurrence for occurrence in occurrences if occurrence.set_name == "VAMOIC"]

    assert len(vamoic) == 1
    assert vamoic[0].inherited is True
    assert vamoic[0].global_id == "0cov0000000000000000000"
    assert vamoic[0].property_names == ("Nosaukums",)


def test_iter_property_set_occurrences_respects_entity_type_filter() -> None:
    occurrences = list(iter_property_set_occurrences(_build_model(), entity_type="IfcCovering"))

    assert {occurrence.ifc_class for occurrence in occurrences} == {"IfcCovering"}


def test_populated_property_names_excludes_blank_values() -> None:
    ifc = ifcopenshell.file(schema="IFC4")
    covering = ifc.create_entity("IfcCovering", GlobalId="0cov0000000000000000000")
    pset = ifc.create_entity(
        "IfcPropertySet",
        GlobalId="0pset000000000000000000",
        Name="VAMOIC",
        HasProperties=[
            ifc.create_entity(
                "IfcPropertySingleValue",
                Name="Nosaukums",
                NominalValue=ifc.create_entity("IfcText", "Griesti"),
            ),
            ifc.create_entity(
                "IfcPropertySingleValue",
                Name="Tips",
                NominalValue=ifc.create_entity("IfcText", "   "),
            ),
            ifc.create_entity("IfcPropertySingleValue", Name="Materiāls"),
        ],
    )
    ifc.create_entity(
        "IfcRelDefinesByProperties",
        GlobalId="0rel1000000000000000000",
        RelatedObjects=[covering],
        RelatingPropertyDefinition=pset,
    )

    occurrence = element_property_set_occurrences(covering)[0]

    assert occurrence.property_names == ("Nosaukums", "Tips", "Materiāls")
    assert occurrence.populated_property_names == ("Nosaukums",)


def test_populated_property_names_ignores_enumeration_reference_without_values() -> None:
    ifc = ifcopenshell.file(schema="IFC4")
    covering = ifc.create_entity("IfcCovering", GlobalId="0cov0000000000000000000")
    enumeration = ifc.create_entity(
        "IfcPropertyEnumeration",
        Name="PEnum_Status",
        EnumerationValues=[
            ifc.create_entity("IfcLabel", "New"),
            ifc.create_entity("IfcLabel", "Existing"),
        ],
    )
    pset = ifc.create_entity(
        "IfcPropertySet",
        GlobalId="0pset000000000000000000",
        Name="Pset_Status",
        HasProperties=[
            ifc.create_entity(
                "IfcPropertyEnumeratedValue",
                Name="Blank",
                EnumerationReference=enumeration,
            ),
            ifc.create_entity(
                "IfcPropertyEnumeratedValue",
                Name="Filled",
                EnumerationValues=[ifc.create_entity("IfcLabel", "New")],
                EnumerationReference=enumeration,
            ),
        ],
    )
    ifc.create_entity(
        "IfcRelDefinesByProperties",
        GlobalId="0rel1000000000000000000",
        RelatedObjects=[covering],
        RelatingPropertyDefinition=pset,
    )

    occurrence = element_property_set_occurrences(covering)[0]

    assert occurrence.property_names == ("Blank", "Filled")
    assert occurrence.populated_property_names == ("Filled",)


def test_populated_property_names_keeps_zero_quantities() -> None:
    ifc = ifcopenshell.file(schema="IFC4")
    duct = ifc.create_entity("IfcDuctSegment", GlobalId="0duct000000000000000000")
    qto = ifc.create_entity(
        "IfcElementQuantity",
        GlobalId="0qto0000000000000000000",
        Name="Qto_DuctSegmentBaseQuantities",
        Quantities=[ifc.create_entity("IfcQuantityLength", Name="Length", LengthValue=0.0)],
    )
    ifc.create_entity(
        "IfcRelDefinesByProperties",
        GlobalId="0rel1000000000000000000",
        RelatedObjects=[duct],
        RelatingPropertyDefinition=qto,
    )

    occurrence = element_property_set_occurrences(duct)[0]

    assert occurrence.populated_property_names == ("Length",)


def test_element_property_set_occurrences_covers_one_element() -> None:
    ifc = _build_model()
    covering = ifc.by_type("IfcCovering")[0]

    occurrences = element_property_set_occurrences(covering)

    assert {occurrence.set_name for occurrence in occurrences} == {
        "XQto_CoveringBaseQuantities",
        "VAMOIC",
    }

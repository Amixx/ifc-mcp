"""Tests for element relationship classification tools."""

from __future__ import annotations

from pathlib import Path
import json

import pytest

from ifc_mcp.core.index import build_index
from ifc_mcp.core.relationships import (
    build_aggregate_map,
    build_storey_container_map,
    build_storey_containment_map,
    get_element_storey_placements,
    has_direct_geometry,
    resolve_storey_for_element,
)
from ifc_mcp.core.types import EntityRecord, ParsedModel, SceneElement, SceneModel
import ifc_mcp.mcp.model_store as model_store
from ifc_mcp.mcp.model_store import ModelStore
from ifc_mcp.tools import relationships


def test_core_relationship_helpers(synthetic_relationship_index):
    contained, containers = build_storey_containment_map(synthetic_relationship_index)
    aggregate_map = build_aggregate_map(synthetic_relationship_index)

    assert contained == {"CURTAIN1"}
    assert containers["CURTAIN1"]["ifc_class"] == "IfcBuildingStorey"
    assert aggregate_map == {
        "MULLION1": "CURTAIN1",
        "MULLION2": "CURTAIN1",
        "MULLION3": "CURTAIN1",
    }
    assert has_direct_geometry(synthetic_relationship_index.by_guid["SLAB1"]) is True


def test_resolve_storey_for_element(synthetic_relationship_index):
    index = synthetic_relationship_index

    # Directly contained element resolves to its storey.
    direct = resolve_storey_for_element(index, "CURTAIN1")
    assert direct is not None and direct["global_id"] == "STOREY1"

    # Decomposition parts (no direct containment) inherit the storey of their whole.
    for part in ("MULLION1", "MULLION2", "MULLION3"):
        inherited = resolve_storey_for_element(index, part)
        assert inherited is not None and inherited["global_id"] == "STOREY1"

    # A true orphan (no containment, no aggregate parent) resolves to no storey.
    assert resolve_storey_for_element(index, "SLAB1") is None


def test_resolve_storey_through_a_spatial_container(spatial_container_index):
    index = spatial_container_index

    # An element sitting in a space resolves to the storey that aggregates the space.
    for guid in ("FURNITURE1", "FURNITURE2"):
        resolved = resolve_storey_for_element(index, guid)
        assert resolved is not None
        assert resolved["global_id"] == "STOREY1"
        assert resolved["ifc_class"] == "IfcBuildingStorey"
        assert resolved["name"] == "Level 1"

    # A part of an element that sits in a space inherits the same storey.
    inherited = resolve_storey_for_element(index, "FURNITURE1_PART")
    assert inherited is not None and inherited["global_id"] == "STOREY1"


def test_resolve_storey_names_no_storey_above_the_storey_level(spatial_container_index):
    index = spatial_container_index

    # A space no storey aggregates leads nowhere, and neither do the elements in it.
    assert resolve_storey_for_element(index, "FURNITURE3") is None

    # Containment directly under IfcBuilding or IfcSite names no storey.
    assert resolve_storey_for_element(index, "SIGN1") is None
    assert resolve_storey_for_element(index, "FENCE1") is None

    # A true orphan still resolves to no storey.
    assert resolve_storey_for_element(index, "SLAB1") is None


def test_resolve_storey_terminates_on_a_containment_cycle(spatial_container_index):
    """A malformed export can make two spaces contain each other."""
    index = spatial_container_index
    index.relationships["spatial_containment"].extend(
        [
            {"container_guid": "SPACE_B", "element_guids": ["SPACE_A"]},
            {"container_guid": "SPACE_A", "element_guids": ["SPACE_B"]},
        ]
    )
    index.relationship_cache.clear()

    assert resolve_storey_for_element(index, "FURNITURE_CYCLIC") is None


def test_classify_elements_by_relation_synthetic(synthetic_relationship_index):
    result = relationships.classify_elements_by_relation(synthetic_relationship_index)

    assert result["summary"] == {
        "total_elements": 5,
        "parent_count": 1,
        "child_count": 3,
        "investigate_count": 1,
        "excluded_count": 0,
    }
    categories = {
        row["global_id"]: row["relation_category"] for row in result["elements"]
    }
    assert categories["CURTAIN1"] == "parent"
    assert categories["MULLION1"] == "child"
    assert categories["MULLION2"] == "child"
    assert categories["MULLION3"] == "child"
    assert categories["SLAB1"] == "investigate"


def test_get_aggregate_relationships_synthetic(synthetic_relationship_index):
    result = relationships.get_aggregate_relationships(synthetic_relationship_index)

    assert result["stats"] == {"parent_count": 1, "child_count": 3}
    assert list(result["parents"]) == ["CURTAIN1"]
    assert [
        child["global_id"] for child in result["parents"]["CURTAIN1"]["children"]
    ] == [
        "MULLION1",
        "MULLION2",
        "MULLION3",
    ]


def test_find_orphans_synthetic(synthetic_relationship_index):
    result = relationships.find_orphans(synthetic_relationship_index)

    assert result["stats"] == {"count": 1, "by_class": {"IfcSlab": 1}}
    assert result["orphans"] == [
        {
            "global_id": "SLAB1",
            "ifc_class": "IfcSlab",
            "name": "Orphan Slab",
            "has_direct_geometry": True,
            "diagnostic": "no_storey_no_aggregate",
        }
    ]


def test_relationship_tools_exclude_classes(synthetic_relationship_index):
    classified = relationships.classify_elements_by_relation(
        synthetic_relationship_index,
        exclude_classes=["IfcMember"],
    )
    orphans = relationships.find_orphans(
        synthetic_relationship_index,
        exclude_classes=["IfcSlab"],
    )

    assert classified["summary"]["total_elements"] == 2
    assert classified["summary"]["excluded_count"] == 3
    assert orphans["stats"]["count"] == 0


def test_relationship_tools_real_fixture_regression(model_index):
    expected_path = (
        Path(__file__).parent
        / "data"
        / "relationships"
        / "building_architecture.expected.json"
    )
    expected = json.loads(expected_path.read_text())

    classified = relationships.classify_elements_by_relation(model_index)
    aggregates = relationships.get_aggregate_relationships(model_index)
    orphans = relationships.find_orphans(model_index)

    actual = {
        "classification_summary": classified["summary"],
        "aggregate_stats": aggregates["stats"],
        "orphan_stats": orphans["stats"],
    }
    assert actual == expected


def test_model_store_file_path_resolution_and_missing_file(
    residential_ifc, monkeypatch
):
    monkeypatch.setattr(model_store, "_LAST_LOADED_PATH", None)
    monkeypatch.setattr(model_store, "_LAST_LOADED_WITH_GEOMETRY", False)
    store = ModelStore()
    resolved = store.resolve(str(residential_ifc))

    assert resolved.by_guid
    with pytest.raises(FileNotFoundError):
        store.resolve("/tmp/ifc-mcp-missing.ifc")
    monkeypatch.setattr(model_store, "_LAST_LOADED_PATH", None)
    monkeypatch.setattr(model_store, "_LAST_LOADED_WITH_GEOMETRY", False)


@pytest.fixture()
def spatial_container_index():
    """A storey whose spaces hold the elements, as Revit exports room-hosted families.

    The furniture carries no containment on the storey and no aggregate parent of its own:
    the only route from element to storey runs through the space it sits in and the
    ``IfcRelAggregates`` that places that space on the storey.
    """
    classes = {
        "SITE1": ("IfcSite", "Site"),
        "BUILDING1": ("IfcBuilding", "Building"),
        "STOREY1": ("IfcBuildingStorey", "Level 1"),
        "SPACE1": ("IfcSpace", "Room 1"),
        "SPACE2": ("IfcSpace", "Room 2"),
        "SPACE_UNPLACED": ("IfcSpace", "Unplaced Room"),
        "SPACE_A": ("IfcSpace", "Room A"),
        "SPACE_B": ("IfcSpace", "Room B"),
        "FURNITURE1": ("IfcFurniture", "Desk 1"),
        "FURNITURE1_PART": ("IfcBuildingElementPart", "Desk 1 top"),
        "FURNITURE2": ("IfcFurniture", "Desk 2"),
        "FURNITURE3": ("IfcFurniture", "Desk 3"),
        "FURNITURE_CYCLIC": ("IfcFurniture", "Desk 4"),
        "SIGN1": ("IfcSign", "Lobby sign"),
        "FENCE1": ("IfcRailing", "Site fence"),
        "SLAB1": ("IfcSlab", "Orphan Slab"),
    }
    entities = {
        guid: EntityRecord(
            global_id=guid, express_id=index, ifc_class=ifc_class, name=name
        )
        for index, (guid, (ifc_class, name)) in enumerate(classes.items(), start=1)
    }
    relationships_payload = {
        "spatial_containment": [
            {"container_guid": "SPACE1", "element_guids": ["FURNITURE1"]},
            {"container_guid": "SPACE2", "element_guids": ["FURNITURE2"]},
            {"container_guid": "SPACE_UNPLACED", "element_guids": ["FURNITURE3"]},
            {"container_guid": "SPACE_A", "element_guids": ["FURNITURE_CYCLIC"]},
            {"container_guid": "BUILDING1", "element_guids": ["SIGN1"]},
            {"container_guid": "SITE1", "element_guids": ["FENCE1"]},
        ],
        "aggregates": [
            {"parent_guid": "SITE1", "child_guids": ["BUILDING1"]},
            {"parent_guid": "BUILDING1", "child_guids": ["STOREY1", "SPACE_UNPLACED"]},
            {"parent_guid": "STOREY1", "child_guids": ["SPACE1", "SPACE2"]},
            {"parent_guid": "FURNITURE1", "child_guids": ["FURNITURE1_PART"]},
        ],
        "voids": [],
        "fills": [],
        "defines_by_type": [],
        "defines_by_properties": [],
        "associates_material": [],
        "assigns_to_group": [],
        "associates_classification": [],
        "spatial_children": {},
    }
    parsed = ParsedModel(
        metadata={"schema": "IFC4"},
        entities=entities,
        relationships=relationships_payload,
        duplicate_guids=[],
    )
    scene = SceneModel(elements={}, spatial_tree={"roots": [], "total_spatial_nodes": 0})
    return build_index(parsed, scene)


@pytest.fixture()
def synthetic_relationship_index():
    storey = EntityRecord(
        global_id="STOREY1",
        express_id=1,
        ifc_class="IfcBuildingStorey",
        name="Level 1",
    )
    curtain = EntityRecord(
        global_id="CURTAIN1",
        express_id=2,
        ifc_class="IfcCurtainWall",
        name="Curtain Wall",
    )
    mullions = [
        EntityRecord(
            global_id=f"MULLION{i}",
            express_id=10 + i,
            ifc_class="IfcMember",
            name=f"Mullion {i}",
        )
        for i in range(1, 4)
    ]
    slab = EntityRecord(
        global_id="SLAB1",
        express_id=20,
        ifc_class="IfcSlab",
        name="Orphan Slab",
        geometry_bounds={"min": [0.0, 0.0, 0.0], "max": [1.0, 1.0, 0.2]},
    )
    entities = {
        "STOREY1": storey,
        "CURTAIN1": curtain,
        "SLAB1": slab,
        **{entity.global_id: entity for entity in mullions},
    }
    relationships_payload = {
        "spatial_containment": [
            {
                "container_guid": "STOREY1",
                "container_name": "Level 1",
                "element_guids": ["CURTAIN1"],
            }
        ],
        "aggregates": [
            {
                "parent_guid": "CURTAIN1",
                "child_guids": ["MULLION1", "MULLION2", "MULLION3"],
            }
        ],
        "voids": [],
        "fills": [],
        "defines_by_type": [],
        "defines_by_properties": [],
        "associates_material": [],
        "assigns_to_group": [],
        "associates_classification": [],
        "spatial_children": {"STOREY1": ["CURTAIN1"]},
    }
    parsed = ParsedModel(
        metadata={"schema": "IFC4"},
        entities=entities,
        relationships=relationships_payload,
        duplicate_guids=[],
    )
    scene = SceneModel(
        elements={
            "CURTAIN1": SceneElement(
                global_id="CURTAIN1",
                category="element",
                label="Curtain Wall",
                floor="Level 1",
                orientation=None,
                is_external=None,
                host_guid=None,
            )
        },
        spatial_tree={"roots": [], "total_spatial_nodes": 0},
    )
    return build_index(parsed, scene)


def test_storey_container_map_keeps_every_containment_edge(synthetic_relationship_index):
    """An element two storeys contain is a defect the collapsed map cannot express."""
    index = synthetic_relationship_index
    index.entities["STOREY2"] = EntityRecord(
        global_id="STOREY2", express_id=99, ifc_class="IfcBuildingStorey", name="Level 2"
    )
    index.by_guid["STOREY2"] = index.entities["STOREY2"]
    index.relationships["spatial_containment"].append(
        {
            "container_guid": "STOREY2",
            "container_name": "Level 2",
            "element_guids": ["CURTAIN1"],
        }
    )
    index.relationship_cache.clear()

    containers = build_storey_container_map(index)

    assert [row["global_id"] for row in containers["CURTAIN1"]] == ["STOREY1", "STOREY2"]
    assert [row["name"] for row in containers["CURTAIN1"]] == ["Level 1", "Level 2"]
    assert "MULLION1" not in containers

    contained, _ = build_storey_containment_map(index)
    assert contained == {"CURTAIN1"}


def test_storey_container_map_omits_non_storey_containers(spatial_container_index):
    containers = build_storey_container_map(spatial_container_index)

    assert containers == {}


def test_space_hosted_elements_are_placed_not_orphaned(spatial_container_index):
    index = spatial_container_index

    orphans = relationships.find_orphans(index)
    classified = relationships.classify_elements_by_relation(index)
    categories = {row["global_id"]: row for row in classified["elements"]}

    orphan_guids = {row["global_id"] for row in orphans["orphans"]}
    assert "FURNITURE1" not in orphan_guids
    assert "FURNITURE2" not in orphan_guids
    assert categories["FURNITURE2"]["relation_category"] == "parent"
    assert categories["FURNITURE2"]["is_contained_in_building_storey"] is False
    assert categories["FURNITURE2"]["spatial_container_class"] == "IfcSpace"

    # A part of a placed element stays a decomposition child, not a parent.
    assert categories["FURNITURE1_PART"]["relation_category"] == "child"

    # Elements the hierarchy places on no storey are still orphans.
    assert {"FURNITURE3", "SIGN1", "FENCE1", "SLAB1"} <= orphan_guids
    assert categories["FURNITURE3"]["relation_category"] == "investigate"


def test_element_storey_placements_cover_every_element(synthetic_relationship_index):
    ifc = FakeElementIfc(
        [
            FakeElement("CURTAIN1", "IfcCurtainWall", "Curtain Wall", "CW-01"),
            FakeElement("MULLION1", "IfcMember", "Mullion 1", None),
            FakeElement("SLAB1", "IfcSlab", "Orphan Slab", None),
        ]
    )

    assert get_element_storey_placements(synthetic_relationship_index, ifc) == [
        {
            "global_id": "CURTAIN1",
            "ifc_class": "IfcCurtainWall",
            "name": "Curtain Wall",
            "tag": "CW-01",
            "storeys": [{"global_id": "STOREY1", "name": "Level 1"}],
        },
        {
            "global_id": "MULLION1",
            "ifc_class": "IfcMember",
            "name": "Mullion 1",
            "tag": None,
            "storeys": [{"global_id": "STOREY1", "name": "Level 1"}],
        },
        {
            "global_id": "SLAB1",
            "ifc_class": "IfcSlab",
            "name": "Orphan Slab",
            "tag": None,
            "storeys": [],
        },
    ]


def test_element_storey_placements_keep_the_classes_a_caller_may_drop(
    synthetic_relationship_index,
):
    """Openings and decomposition parts are the caller's to exclude, not this helper's."""
    ifc = FakeElementIfc(
        [
            FakeElement("OPENING1", "IfcOpeningElement", "Opening", None),
            FakeElement("MULLION2", "IfcMember", "Mullion 2", None),
        ]
    )

    rows = get_element_storey_placements(synthetic_relationship_index, ifc)

    assert [row["ifc_class"] for row in rows] == ["IfcOpeningElement", "IfcMember"]


def test_element_storey_placements_skip_an_element_without_a_global_id(
    synthetic_relationship_index,
):
    ifc = FakeElementIfc(
        [
            FakeElement("", "IfcWall", "Unidentified Wall", None),
            FakeElement("SLAB1", "IfcSlab", "Orphan Slab", None),
        ]
    )

    rows = get_element_storey_placements(synthetic_relationship_index, ifc)

    assert [row["global_id"] for row in rows] == ["SLAB1"]


def test_element_storey_placements_keep_two_storeys_unmerged(synthetic_relationship_index):
    index = synthetic_relationship_index
    index.entities["STOREY2"] = EntityRecord(
        global_id="STOREY2", express_id=99, ifc_class="IfcBuildingStorey", name="Level 2"
    )
    index.by_guid["STOREY2"] = index.entities["STOREY2"]
    index.relationships["spatial_containment"].append(
        {
            "container_guid": "STOREY2",
            "container_name": "Level 2",
            "element_guids": ["CURTAIN1"],
        }
    )
    index.relationship_cache.clear()
    ifc = FakeElementIfc([FakeElement("CURTAIN1", "IfcCurtainWall", "Curtain Wall", None)])

    [row] = get_element_storey_placements(index, ifc)

    assert row["storeys"] == [
        {"global_id": "STOREY1", "name": "Level 1"},
        {"global_id": "STOREY2", "name": "Level 2"},
    ]


def test_element_storey_placements_keep_declaration_order(synthetic_relationship_index):
    ifc = FakeElementIfc(
        [
            FakeElement("SLAB1", "IfcSlab", "Orphan Slab", None),
            FakeElement("CURTAIN1", "IfcCurtainWall", "Curtain Wall", None),
        ]
    )

    rows = get_element_storey_placements(synthetic_relationship_index, ifc)

    assert [row["global_id"] for row in rows] == ["SLAB1", "CURTAIN1"]


class FakeElement:
    def __init__(self, global_id, ifc_class, name, tag):
        self.GlobalId = global_id
        self.Name = name
        self.Tag = tag
        self._ifc_class = ifc_class

    def is_a(self):
        return self._ifc_class


class FakeElementIfc:
    def __init__(self, elements):
        self._elements = elements

    def by_type(self, class_name):
        return list(self._elements) if class_name == "IfcElement" else []

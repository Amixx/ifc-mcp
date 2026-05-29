"""Tests for element relationship classification tools."""

from __future__ import annotations

from pathlib import Path
import json

import pytest

from ifc_mcp.core.index import build_index
from ifc_mcp.core.relationships import (
    build_aggregate_map,
    build_storey_containment_map,
    has_direct_geometry,
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
        row["global_id"]: row["relation_category"]
        for row in result["elements"]
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
    assert [child["global_id"] for child in result["parents"]["CURTAIN1"]["children"]] == [
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
    expected_path = Path(__file__).parent / "data" / "relationships" / "building_architecture.expected.json"
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


def test_model_store_file_path_resolution_and_missing_file(residential_ifc, monkeypatch):
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

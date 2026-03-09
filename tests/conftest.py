"""Shared pytest fixtures for ifc-mcp tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ifc_mcp.core.index import build_index
from ifc_mcp.core.parser import parse_ifc
from ifc_mcp.core.scene import build_scene_model
from ifc_mcp.core.types import EntityRecord, MaterialComponent, ParsedModel, SceneElement, SceneModel


@pytest.fixture(scope="session")
def residential_ifc() -> Path:
    return ROOT / "data" / "Building-Architecture.ifc"


@pytest.fixture(scope="session")
def structural_ifc() -> Path:
    return ROOT / "data" / "Building-Structural.ifc"


@pytest.fixture(scope="session")
def parsed_model(residential_ifc: Path):
    return parse_ifc(str(residential_ifc))


@pytest.fixture(scope="session")
def scene_model(parsed_model):
    return build_scene_model(parsed_model)


@pytest.fixture(scope="session")
def model_index(parsed_model, scene_model):
    return build_index(parsed_model, scene_model)


@pytest.fixture()
def synthetic_index_factory():
    def _factory(with_space: bool = True, with_material: bool = True, with_entities: bool = True):
        if not with_entities:
            parsed = ParsedModel(metadata={}, entities={}, relationships={}, duplicate_guids=[])
            scene = SceneModel(elements={}, spatial_tree={"roots": [], "total_spatial_nodes": 0})
            return build_index(parsed, scene)

        storey = EntityRecord(
            global_id="STOREY1",
            ifc_class="IfcBuildingStorey",
            name="Level 1",
            property_sets={},
        )

        space = EntityRecord(
            global_id="SPACE1",
            ifc_class="IfcSpace",
            name="Room 101",
            property_sets={"Qto_SpaceBaseQuantities": {"NetArea": 12.5}},
        )

        wall = EntityRecord(
            global_id="WALL1",
            ifc_class="IfcWall",
            name="Test Wall",
            property_sets={"Pset_WallCommon": {"IsExternal": True}},
            spatial_container="SPACE1" if with_space else None,
            materials=[MaterialComponent(name="Concrete", thickness=200.0)] if with_material else [],
            geometry_bounds={"min": [0.0, 0.0, 0.0], "max": [1.0, 0.2, 3.0]},
        )

        entities = {
            "STOREY1": storey,
            "WALL1": wall,
        }
        relationships = {
            "spatial_containment": [
                {
                    "container_guid": "STOREY1",
                    "container_name": "Level 1",
                    "element_guids": ["SPACE1"] if with_space else ["WALL1"],
                },
                {
                    "container_guid": "SPACE1",
                    "container_name": "Room 101",
                    "element_guids": ["WALL1"],
                }
                if with_space
                else {
                    "container_guid": "STOREY1",
                    "container_name": "Level 1",
                    "element_guids": ["WALL1"],
                },
            ],
            "aggregates": [],
            "voids": [],
            "fills": [],
            "defines_by_type": [],
            "defines_by_properties": [],
            "associates_material": [],
            "assigns_to_group": [],
            "associates_classification": [],
            "spatial_children": {"STOREY1": ["SPACE1"] if with_space else ["WALL1"]},
        }

        scene_elements = {
            "WALL1": SceneElement(
                global_id="WALL1",
                category="wall",
                label="exterior wall (Level 1)",
                floor="Level 1",
                orientation="north-facing",
                is_external=True,
                host_guid=None,
                hosted_guids=[],
                parent_guid=None,
                child_guids=[],
            )
        }

        if with_space:
            entities["SPACE1"] = space
            scene_elements["SPACE1"] = SceneElement(
                global_id="SPACE1",
                category="space",
                label="space (Level 1)",
                floor="Level 1",
                orientation=None,
                is_external=None,
                host_guid=None,
                hosted_guids=[],
                parent_guid=None,
                child_guids=[],
            )

        parsed = ParsedModel(metadata={"schema": "IFC4"}, entities=entities, relationships=relationships, duplicate_guids=[])
        scene = SceneModel(
            elements=scene_elements,
            spatial_tree={
                "roots": [
                    {
                        "global_id": "STOREY1",
                        "name": "Level 1",
                        "ifc_class": "IfcBuildingStorey",
                        "element_count": 1,
                        "children": [
                            {
                                "global_id": "SPACE1",
                                "name": "Room 101",
                                "ifc_class": "IfcSpace",
                                "element_count": 1,
                                "children": [],
                            }
                        ]
                        if with_space
                        else [],
                    }
                ],
                "total_spatial_nodes": 2 if with_space else 1,
            },
        )
        return build_index(parsed, scene)

    return _factory

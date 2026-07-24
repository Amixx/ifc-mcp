"""Core IFC parsing, scene modeling, and indexing."""

from .geometry import (
    BoundsExtractionResult,
    MeshExtractionResult,
    extract_element_bounds,
    extract_element_bounds_batch,
    extract_element_meshes_batch,
)
from .grids import get_grid_extents
from .index import ModelIndex, build_index
from .parser import parse_ifc, parse_ifc_with_model
from .pipeline import load_model_artifacts, load_model_artifacts_with_ifc
from .scene import build_scene_model

__all__ = [
    "ModelIndex",
    "build_index",
    "parse_ifc",
    "parse_ifc_with_model",
    "build_scene_model",
    "load_model_artifacts",
    "load_model_artifacts_with_ifc",
    "BoundsExtractionResult",
    "MeshExtractionResult",
    "extract_element_bounds",
    "extract_element_bounds_batch",
    "extract_element_meshes_batch",
    "get_grid_extents",
]

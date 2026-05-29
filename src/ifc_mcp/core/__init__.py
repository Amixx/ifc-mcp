"""Core IFC parsing, scene modeling, and indexing."""

from .geometry import BoundsExtractionResult, extract_element_bounds, extract_element_bounds_batch
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
    "extract_element_bounds",
    "extract_element_bounds_batch",
]

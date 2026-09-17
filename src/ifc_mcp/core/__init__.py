"""Core IFC parsing, scene modeling, and indexing."""

from .coordinates import get_site_coordinates
from .geometry import (
    BoundsExtractionResult,
    MeshExtractionResult,
    extract_element_bounds,
    extract_element_bounds_batch,
    extract_element_meshes_batch,
)
from .grids import get_grid_axes, get_grid_extents
from .index import ModelIndex, build_index
from .parser import parse_ifc, parse_ifc_with_model
from .pipeline import load_model_artifacts, load_model_artifacts_with_ifc
from .property_sets import (
    PropertySetKind,
    PropertySetOccurrence,
    QuantityValue,
    element_property_set_occurrences,
    iter_property_set_occurrences,
    iter_quantity_values,
)
from .relationships import get_element_storey_placements
from .scene import build_scene_model
from .simplify import SimplifyResult, needs_simplification, simplify_ifc
from .storeys import get_storey_elevations

__all__ = [
    "BoundsExtractionResult",
    "MeshExtractionResult",
    "ModelIndex",
    "PropertySetKind",
    "PropertySetOccurrence",
    "QuantityValue",
    "SimplifyResult",
    "build_index",
    "build_scene_model",
    "element_property_set_occurrences",
    "extract_element_bounds",
    "extract_element_bounds_batch",
    "extract_element_meshes_batch",
    "get_element_storey_placements",
    "get_grid_axes",
    "get_grid_extents",
    "get_site_coordinates",
    "get_storey_elevations",
    "iter_property_set_occurrences",
    "iter_quantity_values",
    "load_model_artifacts",
    "load_model_artifacts_with_ifc",
    "needs_simplification",
    "parse_ifc",
    "parse_ifc_with_model",
    "simplify_ifc",
]

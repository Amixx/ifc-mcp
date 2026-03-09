"""Shared model-loading pipeline for parser -> scene -> index."""

from __future__ import annotations

import time
from typing import Any, Callable

from ifc_mcp.core.index import ModelIndex, build_index
from ifc_mcp.core.parser import parse_ifc
from ifc_mcp.core.scene import build_scene_model
from ifc_mcp.core.types import ParsedModel, SceneModel

ProgressCallback = Callable[[dict[str, Any]], None]


def load_model_artifacts(
    file_path: str,
    progress_callback: ProgressCallback | None = None,
    extract_geometry: bool = True,
) -> tuple[ParsedModel, SceneModel, ModelIndex]:
    """Load one IFC file and build parsed, scene, and index artifacts."""
    started_at = time.monotonic()
    _emit(progress_callback, {"stage": "pipeline", "message": "Starting model pipeline", "file_path": file_path})

    parsed = parse_ifc(file_path, progress_callback=progress_callback, extract_geometry=extract_geometry)

    scene_started_at = time.monotonic()
    _emit(progress_callback, {"stage": "scene", "message": "Building scene model", "file_path": file_path})
    scene = build_scene_model(parsed)
    _emit(
        progress_callback,
        {
            "stage": "scene",
            "message": "Scene model built",
            "file_path": file_path,
            "elapsed_seconds": round(time.monotonic() - scene_started_at, 2),
        },
    )

    index_started_at = time.monotonic()
    _emit(progress_callback, {"stage": "index", "message": "Building lookup index", "file_path": file_path})
    index = build_index(parsed, scene)
    _emit(
        progress_callback,
        {
            "stage": "index",
            "message": "Lookup index built",
            "file_path": file_path,
            "elapsed_seconds": round(time.monotonic() - index_started_at, 2),
        },
    )

    _emit(
        progress_callback,
        {
            "stage": "ready",
            "message": "Model is ready",
            "file_path": file_path,
            "elapsed_seconds": round(time.monotonic() - started_at, 2),
            "entities": len(parsed.entities),
        },
    )
    return parsed, scene, index


def _emit(callback: ProgressCallback | None, event: dict[str, Any]) -> None:
    if callback is not None:
        callback(event)

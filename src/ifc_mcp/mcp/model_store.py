"""Stateful model store for MCP server sessions."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ifc_mcp.core.index import ModelIndex
from ifc_mcp.core.pipeline import load_model_artifacts

_LAST_LOADED_PATH: str | None = None
_LAST_LOADED_WITH_GEOMETRY: bool = False

ProgressCallback = Callable[[dict[str, Any]], None]


class ModelStore:
    """In-memory cache of loaded IFC models for one server process."""

    def __init__(self, progress_callback: ProgressCallback | None = None) -> None:
        self._cache: dict[tuple[str, bool], ModelIndex] = {}
        self._active_path: str | None = None
        self._active_with_geometry: bool = False
        self._progress_callback = progress_callback

    @property
    def active_path(self) -> str | None:
        """Return currently active model path."""
        return self._active_path

    def normalize_path(self, file_path: str) -> str:
        """Normalize and validate a user-provided IFC file path."""
        path = Path(file_path).expanduser().resolve()
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"IFC file not found: {path}")
        return str(path)

    @property
    def active_with_geometry(self) -> bool:
        """Return whether the active model was loaded with eager geometry."""
        return self._active_with_geometry

    def load(self, file_path: str, with_geometry: bool = False) -> ModelIndex:
        """Load and activate model from file path (cached by absolute path)."""
        global _LAST_LOADED_PATH, _LAST_LOADED_WITH_GEOMETRY
        normalized = self.normalize_path(file_path)
        cache_key = (normalized, with_geometry)
        if cache_key not in self._cache:
            _, _, index = load_model_artifacts(
                normalized,
                progress_callback=self._progress_callback,
                extract_geometry=with_geometry,
            )
            self._cache[cache_key] = index
        self._active_path = normalized
        self._active_with_geometry = with_geometry
        _LAST_LOADED_PATH = normalized
        _LAST_LOADED_WITH_GEOMETRY = with_geometry
        return self._cache[cache_key]

    def set_active_index(self, index: ModelIndex, label: str = "<in-memory>") -> None:
        """Set an already-built index as the active model."""
        key = (label, getattr(index, "geometry_loaded", True))
        self._cache[key] = index
        self._active_path = label
        self._active_with_geometry = getattr(index, "geometry_loaded", True)

    def resolve(self, file_path: str | None = None) -> ModelIndex:
        """Resolve requested model index from explicit file path or active model."""
        if file_path:
            return self.load(file_path, with_geometry=False)
        if self._active_path is None:
            if _LAST_LOADED_PATH is not None:
                return self.load(_LAST_LOADED_PATH, with_geometry=_LAST_LOADED_WITH_GEOMETRY)
            raise ValueError(
                "No IFC model loaded. Call load_model(file_path) first or pass file_path to a tool."
            )
        cache_key = (self._active_path, self._active_with_geometry)
        if cache_key not in self._cache:
            if self._active_path != "<in-memory>":
                return self.load(self._active_path, with_geometry=self._active_with_geometry)
            if _LAST_LOADED_PATH is not None:
                return self.load(_LAST_LOADED_PATH, with_geometry=_LAST_LOADED_WITH_GEOMETRY)
            raise ValueError(
                "No IFC model loaded. Call load_model(file_path) first or pass file_path to a tool."
            )
        return self._cache[cache_key]

    def unload_active(self) -> bool:
        """Unload currently active model from cache."""
        if self._active_path is None:
            return False
        self._cache.pop((self._active_path, self._active_with_geometry), None)
        self._active_path = None
        self._active_with_geometry = False
        return True

    def active_index(self) -> ModelIndex | None:
        """Return active index if one is loaded."""
        if self._active_path is None:
            return None
        return self._cache.get((self._active_path, self._active_with_geometry))

    def status(self) -> dict[str, object]:
        """Get status for loaded/cached model paths."""
        cached_paths = sorted({path for path, _ in self._cache})
        cached_variants = [
            {"file_path": path, "with_geometry": with_geometry}
            for path, with_geometry in sorted(self._cache.keys())
        ]
        return {
            "loaded_model": self._active_path,
            "geometry_loaded": self._active_with_geometry if self._active_path else False,
            "cached_models": cached_paths,
            "cached_variants": cached_variants,
            "cached_count": len(self._cache),
        }

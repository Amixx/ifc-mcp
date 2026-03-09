"""Stateful model store for MCP server sessions."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ifc_mcp.core.index import ModelIndex
from ifc_mcp.core.pipeline import load_model_artifacts

ProgressCallback = Callable[[dict[str, Any]], None]


class ModelStore:
    """In-memory cache of loaded IFC models for one server process."""

    def __init__(self, progress_callback: ProgressCallback | None = None) -> None:
        self._cache: dict[str, ModelIndex] = {}
        self._active_path: str | None = None
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

    def load(self, file_path: str) -> ModelIndex:
        """Load and activate model from file path (cached by absolute path)."""
        normalized = self.normalize_path(file_path)
        if normalized not in self._cache:
            _, _, index = load_model_artifacts(normalized, progress_callback=self._progress_callback)
            self._cache[normalized] = index
        self._active_path = normalized
        return self._cache[normalized]

    def set_active_index(self, index: ModelIndex, label: str = "<in-memory>") -> None:
        """Set an already-built index as the active model."""
        self._cache[label] = index
        self._active_path = label

    def resolve(self, file_path: str | None = None) -> ModelIndex:
        """Resolve requested model index from explicit file path or active model."""
        if file_path:
            return self.load(file_path)
        if self._active_path is None:
            raise ValueError(
                "No IFC model loaded. Call load_model(file_path) first or pass file_path to a tool."
            )
        return self._cache[self._active_path]

    def unload_active(self) -> bool:
        """Unload currently active model from cache."""
        if self._active_path is None:
            return False
        self._cache.pop(self._active_path, None)
        self._active_path = None
        return True

    def status(self) -> dict[str, object]:
        """Get status for loaded/cached model paths."""
        return {
            "loaded_model": self._active_path,
            "cached_models": sorted(self._cache.keys()),
            "cached_count": len(self._cache),
        }

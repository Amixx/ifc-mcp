"""Stateful model store for MCP server sessions."""

from __future__ import annotations

from pathlib import Path

from ifc_mcp.core.index import ModelIndex, build_index
from ifc_mcp.core.parser import parse_ifc
from ifc_mcp.core.scene import build_scene_model


class ModelStore:
    """In-memory cache of loaded IFC models for one server process."""

    def __init__(self) -> None:
        self._cache: dict[str, ModelIndex] = {}
        self._active_path: str | None = None

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
            parsed = parse_ifc(normalized)
            scene = build_scene_model(parsed)
            self._cache[normalized] = build_index(parsed, scene)
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

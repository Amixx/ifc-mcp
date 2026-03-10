"""ifc-mcp package."""

from __future__ import annotations

from importlib import metadata
from pathlib import Path
import re

__all__ = ["__version__"]


def _resolve_version() -> str:
    try:
        return metadata.version("ifc-mcp")
    except metadata.PackageNotFoundError:
        return _read_local_pyproject_version()


def _read_local_pyproject_version() -> str:
    """Fallback for source checkout when distribution metadata is absent."""
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    if not pyproject.exists():
        return "0+unknown"
    try:
        content = pyproject.read_text(encoding="utf-8")
    except OSError:
        return "0+unknown"

    match = re.search(r'^\s*version\s*=\s*"([^"]+)"\s*$', content, re.MULTILINE)
    if not match:
        return "0+unknown"
    return match.group(1)


__version__ = _resolve_version()

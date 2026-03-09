"""Configuration loading for IFC lint rules."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


RECOMMENDED_RULES: dict[str, str] = {
    "no-unnamed-elements": "warn",
    "require-material-assignment": "warn",
    "require-spatial-containment": "warn",
    "no-empty-property-sets": "warn",
    "no-duplicate-guids": "warn",
    "no-dead-types": "warn",
    "require-space-area": "warn",
    "no-zero-volume-elements": "warn",
    "require-classification": "off",
}


def load_lint_config(config_path: str | None = None) -> dict[str, Any]:
    """Load .ifclintrc JSON and resolve rule severities."""
    cfg_path = Path(config_path) if config_path else Path.cwd() / ".ifclintrc"

    base = {
        "extends": "recommended",
        "rules": {},
    }

    if cfg_path.exists():
        with cfg_path.open("r", encoding="utf-8") as handle:
            user_config = json.load(handle)
        base.update({k: v for k, v in user_config.items() if k != "rules"})
        base["rules"] = user_config.get("rules", {})

    resolved = {}
    if base.get("extends") == "recommended":
        resolved.update(RECOMMENDED_RULES)

    for rule_id, severity in base.get("rules", {}).items():
        resolved[rule_id] = severity

    return {
        "extends": base.get("extends", "recommended"),
        "rules": resolved,
        "path": str(cfg_path) if cfg_path.exists() else None,
    }

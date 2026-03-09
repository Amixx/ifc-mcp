"""Lint rule engine."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from ifc_mcp.core.index import build_index
from ifc_mcp.core.parser import parse_ifc
from ifc_mcp.core.scene import build_scene_model
from ifc_mcp.core.types import LintResult

from .config import load_lint_config
from .rules import RULE_FUNCTIONS, RULES


def lint_ifc_model(file_path: str, config_path: str | None = None) -> dict[str, Any]:
    """Run active lint rules against an IFC model."""
    parsed = parse_ifc(file_path)
    scene = build_scene_model(parsed)
    index = build_index(parsed, scene)

    config = load_lint_config(config_path)
    severities: dict[str, str] = config.get("rules", {})

    findings: list[LintResult] = []
    for rule_id, rule_fn in RULE_FUNCTIONS.items():
        severity = severities.get(rule_id, "off")
        if severity == "off":
            continue

        rule_findings = rule_fn(index)
        for finding in rule_findings:
            finding.severity = severity
            findings.append(finding)

    summary = {
        "errors": sum(1 for item in findings if item.severity == "error"),
        "warnings": sum(1 for item in findings if item.severity == "warn"),
        "info": sum(1 for item in findings if item.severity == "info"),
        "total": len(findings),
    }

    return {
        "file": file_path,
        "rules": RULES,
        "config": config,
        "summary": summary,
        "results": [asdict(item) for item in findings],
    }

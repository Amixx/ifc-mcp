"""Lint rule engine."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Callable

from ifc_mcp.core.pipeline import load_model_artifacts
from ifc_mcp.core.types import LintResult

from .config import load_lint_config
from .rules import RULE_FUNCTIONS, RULES


def lint_ifc_model(
    file_path: str,
    config_path: str | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Run active lint rules against an IFC model."""
    _, _, index = load_model_artifacts(file_path, progress_callback=progress_callback)

    config = load_lint_config(config_path)
    severities: dict[str, str] = config.get("rules", {})
    active_rules = [rule_id for rule_id in RULE_FUNCTIONS if severities.get(rule_id, "off") != "off"]

    findings: list[LintResult] = []
    if progress_callback is not None:
        progress_callback(
            {
                "stage": "lint",
                "message": "Running lint rules",
                "processed": 0,
                "total": len(active_rules),
            }
        )
    for processed, rule_id in enumerate(active_rules, start=1):
        rule_fn = RULE_FUNCTIONS[rule_id]
        severity = severities.get(rule_id, "off")
        rule_findings = rule_fn(index)
        for finding in rule_findings:
            finding.severity = severity
            findings.append(finding)
        if progress_callback is not None:
            progress_callback(
                {
                    "stage": "lint",
                    "message": f"Evaluated rule: {rule_id}",
                    "processed": processed,
                    "total": len(active_rules),
                }
            )

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

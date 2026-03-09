"""Tests for lint engine and built-in rules."""

from __future__ import annotations

import json

from ifc_mcp.lint.engine import lint_ifc_model
from ifc_mcp.lint.rules import (
    no_dead_types,
    no_empty_property_sets,
    no_unnamed_elements,
    require_material_assignment,
    require_space_area,
)


def test_lint_runs_on_sample_model(residential_ifc):
    result = lint_ifc_model(str(residential_ifc))
    assert "summary" in result
    assert "results" in result
    assert isinstance(result["summary"]["total"], int)


def test_lint_respects_config_override(tmp_path, residential_ifc):
    cfg = {
        "extends": "recommended",
        "rules": {
            "require-material-assignment": "error",
            "require-classification": "off",
        },
    }
    cfg_path = tmp_path / ".ifclintrc"
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")

    result = lint_ifc_model(str(residential_ifc), str(cfg_path))
    severities = {row["severity"] for row in result["results"] if row["rule_id"] == "require-material-assignment"}
    if severities:
        assert severities == {"error"}


def test_rules_handle_empty_model(synthetic_index_factory):
    index = synthetic_index_factory(with_entities=False)
    assert no_unnamed_elements(index) == []
    assert no_empty_property_sets(index) == []
    assert no_dead_types(index) == []


def test_rule_flags_missing_materials(synthetic_index_factory):
    index = synthetic_index_factory(with_space=True, with_material=False)
    findings = require_material_assignment(index)
    assert findings


def test_rule_handles_no_spaces(synthetic_index_factory):
    index = synthetic_index_factory(with_space=False, with_material=True)
    findings = require_space_area(index)
    assert findings == []

"""Tests for MCP model store dynamic loading behavior."""

from __future__ import annotations

import pytest

from ifc_mcp.mcp.model_store import ModelStore


def test_model_store_loads_and_resolves_model(residential_ifc):
    store = ModelStore()
    index = store.load(str(residential_ifc))
    assert store.active_path is not None
    assert index.by_guid

    resolved = store.resolve()
    assert resolved is index


def test_model_store_requires_loaded_model_when_no_path():
    store = ModelStore()
    with pytest.raises(ValueError):
        store.resolve()


def test_model_store_rejects_missing_file():
    store = ModelStore()
    with pytest.raises(FileNotFoundError):
        store.load("/tmp/does-not-exist.ifc")

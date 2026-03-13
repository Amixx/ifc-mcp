"""Tests for MCP model store dynamic loading behavior."""

from __future__ import annotations

from pathlib import Path

import pytest

import ifc_mcp.mcp.model_store as model_store
from ifc_mcp.mcp.model_store import ModelStore


def test_model_store_loads_and_resolves_model(residential_ifc):
    store = ModelStore()
    index = store.load(str(residential_ifc))
    assert store.active_path is not None
    assert store.active_with_geometry is False
    assert index.by_guid
    assert index.geometry_loaded is False

    resolved = store.resolve()
    assert resolved is index
    status = store.status()
    assert status["geometry_loaded"] is False


def test_model_store_can_load_geometry_variant(residential_ifc):
    store = ModelStore()
    index = store.load(str(residential_ifc), with_geometry=True)
    assert store.active_with_geometry is True
    assert index.geometry_loaded is True
    status = store.status()
    assert status["geometry_loaded"] is True
    assert status["cached_count"] >= 1


def test_model_store_requires_loaded_model_when_no_path():
    store = ModelStore()
    with pytest.raises(ValueError):
        store.resolve()


def test_model_store_rejects_missing_file():
    store = ModelStore()
    with pytest.raises(FileNotFoundError):
        store.load("/tmp/does-not-exist.ifc")


def test_model_store_auto_reload_last_path(residential_ifc, monkeypatch):
    monkeypatch.setattr(model_store, "_LAST_LOADED_PATH", None)
    monkeypatch.setattr(model_store, "_LAST_LOADED_WITH_GEOMETRY", False)

    store_a = ModelStore()
    store_a.load(str(residential_ifc))

    store_b = ModelStore()
    resolved = store_b.resolve()

    assert resolved is not None
    assert store_b.active_path == str(Path(residential_ifc).resolve())

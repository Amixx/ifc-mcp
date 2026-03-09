"""MCP server setup and tool registration for ifc-mcp."""

from __future__ import annotations

from typing import Any, Callable

from ifc_mcp.core.index import ModelIndex
from ifc_mcp.core.pipeline import load_model_artifacts
from ifc_mcp.mcp.model_store import ModelStore
from ifc_mcp.mcp.tools import analysis, meta, quantities, query, relationships, spatial


def load_index(
    file_path: str,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> ModelIndex:
    """Parse IFC file and build the in-memory model index."""
    _, _, index = load_model_artifacts(file_path, progress_callback=progress_callback)
    return index


def create_mcp_server(
    index: ModelIndex | None = None,
    file_path: str | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
):
    """Create FastMCP server instance with all IFC tools registered."""
    try:
        from fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError("fastmcp is required to run the MCP server") from exc

    mcp = FastMCP("ifc-mcp")
    store = ModelStore(progress_callback=progress_callback)

    if index is not None:
        store.set_active_index(index, label=file_path or "<in-memory>")
    elif file_path:
        store.load(file_path)

    def _resolve_index(request_file_path: str | None) -> tuple[ModelIndex | None, dict[str, Any] | None]:
        try:
            return store.resolve(request_file_path), None
        except Exception as exc:
            return None, {
                "error": str(exc),
                "hint": "Call load_model(file_path) first or pass file_path to this tool.",
            }

    @mcp.tool()
    def load_model(file_path: str) -> dict[str, Any]:
        """Load or switch the active IFC model from an absolute file path for subsequent tool calls."""
        try:
            index_obj = store.load(file_path)
            return {
                "loaded_model": store.active_path,
                "summary": meta.get_model_summary(index_obj),
                "cached_models": store.status()["cached_models"],
            }
        except Exception as exc:
            return {"error": str(exc), "file_path": file_path}

    @mcp.tool()
    def get_loaded_model() -> dict[str, Any]:
        """Get currently loaded IFC model path and cached model list for this server session."""
        return store.status()

    @mcp.tool()
    def unload_model() -> dict[str, Any]:
        """Unload the currently active IFC model from this server session."""
        unloaded = store.unload_active()
        status = store.status()
        status["unloaded"] = unloaded
        return status

    @mcp.tool()
    def get_element_by_id(global_id: str, file_path: str | None = None) -> dict[str, Any]:
        """Get full details for one element by GlobalId. If file_path is set, that file is loaded first."""
        index_obj, err = _resolve_index(file_path)
        if err:
            return err
        return query.get_element_by_id(index_obj, global_id)

    @mcp.tool()
    def search_elements(
        ifc_class: str | None = None,
        name: str | None = None,
        floor: str | None = None,
        material: str | None = None,
        file_path: str | None = None,
    ) -> dict[str, Any]:
        """Search elements by optional class/name/floor/material filters; optionally load specific file_path."""
        index_obj, err = _resolve_index(file_path)
        if err:
            return err
        return query.search_elements(index_obj, ifc_class=ifc_class, name=name, floor=floor, material=material)

    @mcp.tool()
    def get_element_properties(global_id: str, file_path: str | None = None) -> dict[str, Any]:
        """Get all property sets for one element; optionally resolve from file_path."""
        index_obj, err = _resolve_index(file_path)
        if err:
            return err
        return query.get_element_properties(index_obj, global_id)

    @mcp.tool()
    def get_spatial_structure(file_path: str | None = None) -> dict[str, Any]:
        """Get full Site -> Building -> Storey -> Space hierarchy for active or provided file_path."""
        index_obj, err = _resolve_index(file_path)
        if err:
            return err
        return spatial.get_spatial_structure(index_obj)

    @mcp.tool()
    def get_elements_in_space(space_id: str, file_path: str | None = None) -> dict[str, Any]:
        """Get all elements in a room/space/storey/container for active or provided file_path."""
        index_obj, err = _resolve_index(file_path)
        if err:
            return err
        return spatial.get_elements_in_space(index_obj, space_id)

    @mcp.tool()
    def get_connected_elements(global_id: str, file_path: str | None = None) -> dict[str, Any]:
        """Get hosted/void/fill/aggregate connections for active or provided file_path."""
        index_obj, err = _resolve_index(file_path)
        if err:
            return err
        return relationships.get_connected_elements(index_obj, global_id)

    @mcp.tool()
    def get_contained_elements(global_id: str, file_path: str | None = None) -> dict[str, Any]:
        """Get children from spatial containment and aggregation for active or provided file_path."""
        index_obj, err = _resolve_index(file_path)
        if err:
            return err
        return relationships.get_contained_elements(index_obj, global_id)

    @mcp.tool()
    def get_element_material(global_id: str, file_path: str | None = None) -> dict[str, Any]:
        """Get assigned material layers/constituents/list for element from active or provided file_path."""
        index_obj, err = _resolve_index(file_path)
        if err:
            return err
        return relationships.get_element_material(index_obj, global_id)

    @mcp.tool()
    def get_quantities(
        ifc_class: str | None = None,
        floor: str | None = None,
        material: str | None = None,
        file_path: str | None = None,
    ) -> dict[str, Any]:
        """Get aggregated quantities (count, area, volume, length) for active or provided file_path."""
        index_obj, err = _resolve_index(file_path)
        if err:
            return err
        return quantities.get_quantities(index_obj, ifc_class=ifc_class, floor=floor, material=material)

    @mcp.tool()
    def get_material_summary(file_path: str | None = None) -> dict[str, Any]:
        """Get material usage summary for active or provided file_path."""
        index_obj, err = _resolve_index(file_path)
        if err:
            return err
        return quantities.get_material_summary(index_obj)

    @mcp.tool()
    def get_space_summary(floor: str | None = None, file_path: str | None = None) -> dict[str, Any]:
        """Get space area/volume/count summary for active or provided file_path."""
        index_obj, err = _resolve_index(file_path)
        if err:
            return err
        return quantities.get_space_summary(index_obj, floor=floor)

    @mcp.tool()
    def find_elements_by_property(
        property_name: str,
        value: str | None = None,
        operator: str | None = None,
        file_path: str | None = None,
    ) -> dict[str, Any]:
        """Find elements by property across active or provided file_path."""
        index_obj, err = _resolve_index(file_path)
        if err:
            return err
        return analysis.find_elements_by_property(index_obj, property_name=property_name, value=value, operator=operator)

    @mcp.tool()
    def get_classification(global_id: str, file_path: str | None = None) -> dict[str, Any]:
        """Get classification references for element from active or provided file_path."""
        index_obj, err = _resolve_index(file_path)
        if err:
            return err
        return analysis.get_classification(index_obj, global_id)

    @mcp.tool()
    def get_type_info(global_id: str, file_path: str | None = None) -> dict[str, Any]:
        """Get type/family info for element from active or provided file_path."""
        index_obj, err = _resolve_index(file_path)
        if err:
            return err
        return analysis.get_type_info(index_obj, global_id)

    @mcp.tool()
    def get_model_summary(file_path: str | None = None) -> dict[str, Any]:
        """Get high-level model summary for active model or provided file_path."""
        index_obj, err = _resolve_index(file_path)
        if err:
            return err
        return meta.get_model_summary(index_obj)

    @mcp.tool()
    def list_property_sets(ifc_class: str | None = None, file_path: str | None = None) -> dict[str, Any]:
        """List pset names with occurrence counts for active or provided file_path."""
        index_obj, err = _resolve_index(file_path)
        if err:
            return err
        return meta.list_property_sets(index_obj, ifc_class=ifc_class)

    @mcp.tool()
    def get_element_geometry_bounds(global_id: str, file_path: str | None = None) -> dict[str, Any]:
        """Get element bounding box for active model or provided file_path."""
        index_obj, err = _resolve_index(file_path)
        if err:
            return err
        return meta.get_element_geometry_bounds(index_obj, global_id)

    return mcp


def run_server(
    file_path: str | None = None,
    transport: str = "stdio",
    port: int = 8000,
    host: str = "127.0.0.1",
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> None:
    """Run the MCP server with stdio or HTTP transport."""
    mcp = create_mcp_server(file_path=file_path, progress_callback=progress_callback)

    if transport == "stdio":
        if hasattr(mcp, "run"):
            mcp.run()
            return
        if hasattr(mcp, "run_stdio"):
            mcp.run_stdio()
            return
        raise RuntimeError("FastMCP instance does not expose stdio run method")

    if transport == "http":
        if hasattr(mcp, "run"):
            try:
                mcp.run(transport="http", host=host, port=port)
                return
            except TypeError:
                mcp.run(transport="streamable-http", host=host, port=port)
                return

        if hasattr(mcp, "run_http"):
            mcp.run_http(host=host, port=port)
            return

        raise RuntimeError("FastMCP instance does not expose HTTP run method")

    raise ValueError(f"Unsupported transport: {transport}")

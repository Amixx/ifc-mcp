# /ifc-summary

Generate a full IFC model report for the currently loaded model.

Usage:

```text
/ifc-summary
```

Execution steps:

1. Call `mcp__ifc_mcp__get_loaded_model()`
2. If no model is loaded, stop and instruct user to run:
   - `/load-ifc /absolute/path/to/model.ifc`
3. Otherwise call:
   - `mcp__ifc_mcp__get_model_summary()`
   - `mcp__ifc_mcp__get_spatial_structure()`
   - `mcp__ifc_mcp__get_space_summary()`
   - `mcp__ifc_mcp__get_material_summary()`

Report sections:

- Overview (schema, metadata, element totals)
- Element counts by IFC class
- Spatial structure snapshot (site/building/storeys/spaces)
- Space area/volume summary
- Material breakdown (counts + total area/volume)

Style:

- Use concise tables where possible
- Round quantities to 2 decimals
- Include GUIDs only when listing individual elements

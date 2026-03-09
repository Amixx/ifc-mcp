# /load-ifc

Load an IFC model into MCP session and return a concise overview.

Usage:

```text
/load-ifc /absolute/path/to/model.ifc
```

Execution steps:

1. Call `mcp__ifc_mcp__load_model(file_path="<path>")`
2. Call `mcp__ifc_mcp__get_model_summary()`
3. Call `mcp__ifc_mcp__get_spatial_structure()`

Response format:

- Loaded file path
- Project/model label (if available from metadata/name fields)
- Schema version
- Top element types (top 5 by count)
- Storey list

If loading fails, return the error from `load_model` and suggest checking absolute path and file permissions.

# ifc-mcp

Production-focused MCP server for querying IFC (Industry Foundation Classes) building models.

## Install

```bash
pip install ifc-mcp
```

## Quick start

```bash
# MCP server over stdio (Claude Desktop / Cursor)
ifc-mcp serve path/to/model.ifc

# MCP server over HTTP
ifc-mcp serve path/to/model.ifc --transport http --port 8000

# Start once without preloading a model (recommended for global setup)
ifc-mcp serve

# Quick model summary
ifc-mcp info path/to/model.ifc

# Lint model
ifc-mcp lint path/to/model.ifc

# Lightweight deterministic diff
ifc-mcp diff old.ifc new.ifc
```

Claude Desktop config:

```json
{
  "mcpServers": {
    "ifc": {
      "command": "ifc-mcp",
      "args": ["serve"]
    }
  }
}
```

## Architecture

`ifc-mcp` is split into layers:

- `ifc_mcp/core/`: no MCP dependency, parses IFC and builds scene/index structures.
- `ifc_mcp/mcp/`: MCP server + tool wrappers over the core index.
- `ifc_mcp/lint/`: rule engine + built-in model quality rules.
- `ifc_mcp/diff/`: deterministic model diff engine.
- `ifc_mcp/cli.py`: `serve`, `info`, `lint`, `diff` commands.

## Implemented MCP tools

Session/model management:

- `load_model(file_path)`
- `get_loaded_model()`
- `unload_model()`

All query tools can also receive optional `file_path` to resolve a model directly.

### Query
- `get_element_by_id(global_id)`
- `search_elements(ifc_class, name, floor, material)`
- `get_element_properties(global_id)`

### Spatial
- `get_spatial_structure()`
- `get_elements_in_space(space_id)`

### Relationships
- `get_connected_elements(global_id)`
- `get_contained_elements(global_id)`
- `get_element_material(global_id)`

### Quantities
- `get_quantities(ifc_class, floor, material)`
- `get_material_summary()`
- `get_space_summary(floor)`

### Analysis
- `find_elements_by_property(property_name, value, operator)`
- `get_classification(global_id)`
- `get_type_info(global_id)`

### Meta
- `get_model_summary()`
- `list_property_sets(ifc_class)`
- `get_element_geometry_bounds(global_id)`

## Linting

Default preset (`recommended`): all built-in rules are `warn` except `require-classification` (`off`).

Example `.ifclintrc`:

```json
{
  "extends": "recommended",
  "rules": {
    "no-unnamed-elements": "warn",
    "require-material-assignment": "error",
    "require-classification": "off",
    "require-space-area": "warn"
  }
}
```

CI behavior: `ifc-mcp lint ...` exits with code `1` when any `error` findings are present.

## Testing

Run tests with:

```bash
PYTHONPATH=src pytest
```

Included IFC fixtures from `data/`:

- `data/Building-Architecture.ifc`
- `data/Building-Structural.ifc`
- `data/Building-Hvac.ifc`

These are used by parser/index/tool/lint tests.

## Domain implementation notes

- Hosting chains resolve `IfcRelVoidsElement` + `IfcRelFillsElement` into direct wall→door/window links.
- Wall orientation uses placement local X-axis and IFC compass convention (`+Y=north`, `+X=east`).
- Exterior/interior labels are driven by `Pset_*Common.IsExternal`, with safe name-based fallback.
- Material extraction handles `IfcMaterial`, `IfcMaterialLayerSetUsage`, `IfcMaterialConstituentSet`, `IfcMaterialList` (plus profile-set variants).
- Classification extraction uses `IfcRelAssociatesClassification` and normalizes system/reference/identification.
- Missing real-world data is handled gracefully (empty arrays/dicts instead of exceptions).

## License

MIT

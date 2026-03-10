# ifc-mcp

MCP server for exploring and querying IFC (Industry Foundation Classes) building models.

## Install

```bash
pip install ifc-mcp
```

`ifc-mcp` must be on your `PATH` for MCP clients that use `command: "ifc-mcp"`.

```bash
which ifc-mcp
ifc-mcp --help
ifc-mcp --version
```

## Run

Start once and load models dynamically during chat:

```bash
ifc-mcp serve
```

Optional preload:

```bash
ifc-mcp serve /absolute/path/to/model.ifc
```

HTTP transport:

```bash
ifc-mcp serve --transport http --port 8000
```

## MCP client config

```json
{
  "mcpServers": {
    "ifc_mcp": {
      "command": "ifc-mcp",
      "args": ["serve"]
    }
  }
}
```

## Typical workflow in chat

1. `load_model(file_path="/absolute/path/to/model.ifc")` (fast default)
2. `get_model_summary()`
3. Query with tools by element, space, material, property, or type.

Most tools also accept optional `file_path` for one-shot queries.

Geometry is loaded lazily by default for speed. Use eager mode only when needed:

- MCP tool: `load_model(file_path="...", with_geometry=true)`
- CLI preload: `ifc-mcp serve /absolute/path/to/model.ifc --with-geometry`
- Session status: `get_loaded_model()` includes `geometry_loaded`

## License

[MIT](LICENSE)

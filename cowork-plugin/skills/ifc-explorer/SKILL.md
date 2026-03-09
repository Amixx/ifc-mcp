# IFC Explorer

Use this skill when the user wants to load, inspect, query, compare, or analyze IFC building model files.

## Trigger cues

- "Open this IFC"
- "Analyze this building model"
- "Find all walls/doors/windows"
- "How much floor area/material volume"
- "Show structure/storeys/spaces"

## Workflow

1. Check session state first:
   - `mcp__ifc_mcp__get_loaded_model`
2. If no model is loaded (or user wants another file), load one:
   - `mcp__ifc_mcp__load_model(file_path="/absolute/path/to/model.ifc")`
3. Start orientation with:
   - `mcp__ifc_mcp__get_model_summary`
4. Then drill down with the right tool group.

Most tools also accept optional `file_path` to run directly against a specific file without changing current session state.

## Tool group usage

### Session

- `load_model`: Set/switch active IFC model.
- `get_loaded_model`: Check active model and cache.
- `unload_model`: Clear active model.

### Spatial

Use when user asks where elements are, how storeys/spaces are organized, or what is in a room.

- `get_spatial_structure`
- `get_elements_in_space`

### Query

Use for element lookup and filtered search.

- `get_element_by_id`
- `search_elements`
- `get_element_properties`

### Relationships

Use for connectivity, containment, host chains, materials per element.

- `get_connected_elements`
- `get_contained_elements`
- `get_element_material`

### Quantities

Use for totals and rollups.

- `get_quantities`
- `get_material_summary`
- `get_space_summary`

### Analysis

Use for semantic filtering and classification/type context.

- `find_elements_by_property`
- `get_classification`
- `get_type_info`

### Meta

Use for model-wide orientation and discovery.

- `get_model_summary`
- `list_property_sets`
- `get_element_geometry_bounds`

## Common patterns

- "How many m2 of floor space?"
  - `get_space_summary` then sum/compare area by floor.
- "Find fire-rated walls"
  - `find_elements_by_property(property_name="FireRating", operator="exists"|"equals")`
  - then `search_elements(ifc_class="IfcWall")` as needed.
- "What is this element?"
  - `get_element_by_id` then `get_type_info` and `get_element_material`.
- "What is on Level 2?"
  - `search_elements(floor="Level 2")` and `get_space_summary(floor="Level 2")`.

## Response style

- Interpret results, do not just dump raw JSON.
- Prefer compact tables for counts, area, volume, and type breakdowns.
- Round quantities (typically 2 decimals unless precision matters).
- Include GlobalIds for traceability when listing elements.
- Call out missing data explicitly (e.g. no spaces, no classifications).

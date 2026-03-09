# ifc-mcp Tools Reference

All tools are exposed as `mcp__ifc_mcp__<tool_name>`.

Notes:

- `file_path` is optional on most tools and can be used for one-shot file queries.
- If no `file_path` is provided, the active session model is used.
- `load_model` is the main way to set active model state.

## Session tools

### `load_model(file_path: str)`

Loads/switches active IFC model.

Parameters:

- `file_path` (required, absolute path recommended)

### `get_loaded_model()`

Returns active model path, cache list, cache count.

Parameters:

- none

### `unload_model()`

Unloads active model.

Parameters:

- none

## Query tools

### `get_element_by_id(global_id: str, file_path: str | None = None)`

Returns full element details.

Parameters:

- `global_id` (required)
- `file_path` (optional)

### `search_elements(ifc_class: str | None = None, name: str | None = None, floor: str | None = None, material: str | None = None, file_path: str | None = None)`

AND-filtered search.

Parameters:

- `ifc_class` (optional)
- `name` (optional, case-insensitive substring)
- `floor` (optional)
- `material` (optional)
- `file_path` (optional)

### `get_element_properties(global_id: str, file_path: str | None = None)`

Returns element property sets.

Parameters:

- `global_id` (required)
- `file_path` (optional)

## Spatial tools

### `get_spatial_structure(file_path: str | None = None)`

Returns Site/Building/Storey/Space hierarchy with counts.

Parameters:

- `file_path` (optional)

### `get_elements_in_space(space_id: str, file_path: str | None = None)`

Returns elements in a space/storey/container.

Parameters:

- `space_id` (required; GlobalId or name)
- `file_path` (optional)

## Relationship tools

### `get_connected_elements(global_id: str, file_path: str | None = None)`

Returns connected/hosted/void/fill/aggregate links.

Parameters:

- `global_id` (required)
- `file_path` (optional)

### `get_contained_elements(global_id: str, file_path: str | None = None)`

Returns contained children (spatial + aggregate).

Parameters:

- `global_id` (required)
- `file_path` (optional)

### `get_element_material(global_id: str, file_path: str | None = None)`

Returns element material layers/constituents.

Parameters:

- `global_id` (required)
- `file_path` (optional)

## Quantity tools

### `get_quantities(ifc_class: str | None = None, floor: str | None = None, material: str | None = None, file_path: str | None = None)`

Returns aggregated count/area/volume/length.

Parameters:

- `ifc_class` (optional)
- `floor` (optional)
- `material` (optional)
- `file_path` (optional)

### `get_material_summary(file_path: str | None = None)`

Returns material usage summary.

Parameters:

- `file_path` (optional)

### `get_space_summary(floor: str | None = None, file_path: str | None = None)`

Returns per-space name/floor/area/volume/element counts.

Parameters:

- `floor` (optional)
- `file_path` (optional)

## Analysis tools

### `find_elements_by_property(property_name: str, value: str | None = None, operator: str | None = None, file_path: str | None = None)`

Finds elements by property criteria.

Parameters:

- `property_name` (required)
- `value` (optional)
- `operator` (optional; `exists`, `equals`, `contains`)
- `file_path` (optional)

### `get_classification(global_id: str, file_path: str | None = None)`

Returns classification references.

Parameters:

- `global_id` (required)
- `file_path` (optional)

### `get_type_info(global_id: str, file_path: str | None = None)`

Returns type/family info and instances.

Parameters:

- `global_id` (required)
- `file_path` (optional)

## Meta tools

### `get_model_summary(file_path: str | None = None)`

Returns high-level model overview.

Parameters:

- `file_path` (optional)

### `list_property_sets(ifc_class: str | None = None, file_path: str | None = None)`

Lists property set names + counts.

Parameters:

- `ifc_class` (optional)
- `file_path` (optional)

### `get_element_geometry_bounds(global_id: str, file_path: str | None = None)`

Returns element bbox min/max XYZ.

Parameters:

- `global_id` (required)
- `file_path` (optional)

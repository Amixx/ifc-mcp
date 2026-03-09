# AGENTS.md

## What was built

`ifc-mcp` now includes:

- IFC core parser (`parse_ifc`) with metadata, entities, relationships, materials, classifications, owner history, and geometry bounds extraction.
- Scene model builder (`build_scene_model`) with hosting chains, spatial hierarchy, wall orientation, exterior/interior classification, and human-readable labels.
- In-memory `ModelIndex` with fast lookup maps (`by_guid`, `by_type`, `by_floor`, `by_material`, `by_space`, `type_map`, `spatial_tree`).
- 17 MCP tools across query/spatial/relationships/quantities/analysis/meta modules.
- FastMCP server wiring for all tools.
- Click CLI with `serve`, `info`, `lint`, and deterministic `diff` commands.
- Lint engine with configurable `.ifclintrc` and built-in rule set.
- Test suite (`34` passing tests) covering parser/scene/index/tools/lint + edge-case synthetic models.
- Raw IFC fixtures are consumed directly from `data/` (no duplicated copies in `sample_models/`).

## Why this structure

- `core/` is MCP-agnostic so it can be extracted into shared libraries later.
- `tools/` depend only on `ModelIndex`, keeping server transport concerns out of domain logic.
- Lint rules are isolated pure functions, making severity policy configurable in one place (`lint/config.py`).

## Domain insights captured in code

- IFC relationship traversal requires explicit chaining of void/fill relations to produce user-meaningful host relationships.
- Spatial containment is inconsistent across models; code treats missing containers as valid input and returns empty results instead of errors.
- Type and occurrence data are both needed for LLM queries (`get_type_info`) and lint checks (`no-dead-types`).
- Model metadata and pset/quantity availability vary widely by authoring tool; extraction logic is defensive by design.

## Notes for future contributors

- Keep parser output schema stable; many tool/lint functions assume these keys.
- If adding geometry-heavy features, consider lazy/on-demand geometry extraction to avoid startup cost on large models.
- Keep new tool functions pure (`index` in, JSON-serializable dict out).
- Preserve deterministic behavior across parser/index/lint/diff (no non-deterministic ordering in outputs).

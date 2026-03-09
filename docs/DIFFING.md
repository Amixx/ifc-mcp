# DIFFING

## Command

```bash
ifc-mcp diff <old.ifc> <new.ifc> [--format text|json]
```

## Behavior

Diffing is deterministic and structural:

- Added entities
- Removed entities
- Changed entities (based on stable entity signatures)

No AI is used in the diff pipeline.

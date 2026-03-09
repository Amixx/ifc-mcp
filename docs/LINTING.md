# LINTING

## Command

```bash
ifc-mcp lint <file.ifc> [--config .ifclintrc] [--format text|json]
```

The command exits with code `1` if any findings have severity `error`.

## Config

Lint config is JSON (`.ifclintrc`):

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

`recommended` enables all built-in rules at `warn` except `require-classification` (`off`).

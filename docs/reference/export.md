# Export format

The `export` stage writes:

```text
runs/<RUN_ID>/artifacts/output/database.json
```

## Shape

```json
{
  "generated_at": "...",
  "run_id": "...",
  "schemas": ["record"],
  "stats": {
    "n_papers": 0,
    "by_schema": {},
    "missing_schemas": {}
  },
  "papers": [
    {
      "paper_id": "10.1000_example",
      "record": {
        "schema_name": "record",
        "payload": {},
        "validation": { "valid": true, "errors": [] }
      }
    }
  ]
}
```

## Rules

- Only papers with successful `extract_schema` status are included.
- Each configured schema is present as a full **envelope** or `null` if missing.
- Per-paper files remain under `artifacts/extractions/<paper_id>/`.

## Downstream use

1. Treat LitCurate as the producer of `database.json`.
2. Map envelopes to your models using **your** schema field names.
3. Do not assume a fixed scientific vocabulary beyond what your config defines.

# Concepts

## Pipeline, not a single script

LitCurate is a sequence of **stages**. Each stage:

1. Reads artifacts from earlier stages  
2. Writes new artifacts under `runs/<RUN_ID>/artifacts/`  
3. Records status in a SQLite ledger (`run.db`)

You can run one stage at a time, resume after failures, or force a re-run.

## Config over code

A **config YAML** defines the research goal, search settings, filter criteria, LLM providers, schemas, and prompts. Changing domain usually means editing YAML and schema/prompt files — not Python.

## Schemas and envelopes

Extraction writes **envelopes**: schema metadata, model name, timestamp, validation result, and a `payload` matching your schema. The [export](../reference/export.md) stage merges successful papers into `database.json`.

## Runs are ephemeral

Everything under `runs/` is **runtime output** (PDFs, markdown, extractions, databases). It is not part of the published package. Treat experimental campaigns as disposable usage of LitCurate.

## Integration model

```text
LitCurate  →  database.json  →  your app / database / notebook
```

Downstream code should consume the export (or per-paper envelopes) using field names from **your** schemas.

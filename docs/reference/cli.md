# CLI

```bash
litcurate --help
```

## Commands

| Command | Purpose |
|---------|---------|
| `run` | Start a new full pipeline run |
| `run-stage` | Run a single stage |
| `resume` | Continue a run; optional `--from-stage` / `--until-stage` |
| `status` | Show stage statuses from SQLite |
| `show` | Inspect the primary artifact for a stage |
| `stages` | List stages and primary artifacts |
| `list-runs` | List recent runs |
| `ingest-pdfs` | Register manually downloaded PDFs |
| `merge-filtered` | Merge `papers_filtered.parquet` from another run |
| `reset-stage` | Clear artifacts and mark a stage pending |
| `normalize-manifests` | Rewrite absolute paths in manifests to run-relative |

## Common usage

```bash
litcurate run-stage <stage> --run-id $RUN_ID --config $CONFIG
litcurate run-stage <stage> --run-id $RUN_ID --config $CONFIG --force
litcurate resume $RUN_ID --from-stage extract_schema --until-stage export
litcurate status $RUN_ID
litcurate show extract_schema $RUN_ID
```

`marker-pdf` is included in the base install.

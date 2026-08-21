# Artifacts and resume

Each run lives under:

```text
runs/<RUN_ID>/
  run.db                 # SQLite status / resume
  config.snapshot.yaml   # frozen config for this run
  artifacts/             # stage outputs
  logs/
```

## Primary artifacts

| Stage | Primary artifact |
|--------|------------------|
| `query_generation` | `artifacts/queries.json` |
| `openalex_search` | `artifacts/openalex_raw/` |
| `merge_rank` | `artifacts/papers_ranked.parquet` |
| `filter_abstracts` | `artifacts/papers_filtered.parquet` |
| `download_pdfs` | `artifacts/download_manifest.json` |
| `convert_marker` | `artifacts/convert_manifest.json` |
| `clean_markdown` | `artifacts/clean_manifest.json` |
| `pre_extract` | `artifacts/pre_extract_manifest.json` |
| `filter_fulltext` | `artifacts/fulltext_filter_manifest.json` |
| `extract_schema` | `artifacts/extract_manifest.json` |
| `export` | `artifacts/output/database.json` |

Per-paper extractions: `artifacts/extractions/<paper_id>/*.json`.

## Resume and reset

```bash
litcurate resume $RUN_ID
litcurate resume $RUN_ID --from-stage extract_schema
litcurate reset-stage extract_schema --run-id $RUN_ID
```

`reset-stage` clears that stage’s artifacts (and can clear downstream stages) and marks them pending.

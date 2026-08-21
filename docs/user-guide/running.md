# Running a pipeline

Prefer **stage-by-stage** execution for long jobs.

```bash
cd litcurate
source .venv/bin/activate
export CONFIG=configs/config.yaml
```

## Create a run

```bash
litcurate run-stage query_generation --config $CONFIG
RUN_ID=<printed_run_id>
```

## Recommended sequence

```bash
litcurate run-stage openalex_search --run-id $RUN_ID
litcurate run-stage merge_rank --run-id $RUN_ID
litcurate run-stage filter_abstracts --run-id $RUN_ID --config $CONFIG
litcurate run-stage download_pdfs --run-id $RUN_ID
# Optional: ingest PDFs downloaded manually for missing papers (see below)
litcurate run-stage convert_marker --run-id $RUN_ID
litcurate run-stage clean_markdown --run-id $RUN_ID
litcurate run-stage pre_extract --run-id $RUN_ID
litcurate run-stage filter_fulltext --run-id $RUN_ID --config $CONFIG
litcurate run-stage extract_schema --run-id $RUN_ID --config $CONFIG
litcurate run-stage export --run-id $RUN_ID
```

!!! note "Config on LLM stages"
    Pass `--config $CONFIG` on stages that call an LLM so provider and model settings are applied (avoids a stale snapshot).

## Long jobs on a server

```bash
mkdir -p runs/$RUN_ID/logs
nohup litcurate run-stage convert_marker --run-id $RUN_ID \
  > runs/$RUN_ID/logs/convert_marker.nohup.log 2>&1 &
tail -f runs/$RUN_ID/logs/convert_marker.nohup.log
```

## Status and resume

```bash
litcurate list-runs
litcurate status $RUN_ID
litcurate show <stage_name> $RUN_ID
litcurate resume $RUN_ID
litcurate resume $RUN_ID --from-stage extract_schema
```

Re-run one stage after a config change:

```bash
litcurate run-stage filter_abstracts --run-id $RUN_ID --config $CONFIG --force
```

## Optional: add missing PDFs manually

Run this **after `download_pdfs` and before `convert_marker`** when automatic
download misses paywalled or unavailable papers.

Download the missing PDFs manually into one folder. Name each file using its DOI,
replacing `/` with `_`:

| DOI | Filename |
|-----|----------|
| `10.1029/2011jb008988` | `10.1029_2011jb008988.pdf` |

```bash
litcurate ingest-pdfs --run-id $RUN_ID --from-dir ~/manual_pdfs/ --dry-run
litcurate ingest-pdfs --run-id $RUN_ID --from-dir ~/manual_pdfs/
litcurate status $RUN_ID
litcurate run-stage convert_marker --run-id $RUN_ID
```

`--dry-run` previews which files match papers in the run. The real command copies
matched PDFs into the run and updates the download manifest. Files that do not match
a tracked `paper_id` are reported as unknown.

!!! note
    `ingest-pdfs` is an optional CLI operation, not a numbered pipeline stage.
    If `convert_marker` already ran before you added PDFs, re-run it with `--force`.

## One-shot run

```bash
litcurate run $CONFIG
```

Useful for dry-run or short configs. Prefer stages for large campaigns.

Stage list: [Stages](../reference/stages.md).

---
title: LitCurate
hide:
  - navigation
  - toc
---

# LitCurate

Config-driven pipeline from research goal to structured literature database.

<div class="grid cards" markdown>

-   :material-lightning-bolt-outline: **Fast to start**

    ---

    Install, copy `.env`, run the dry-run config.
    [Installation →](user-guide/installation.md)

-   :material-cog-outline: **Config over code**

    ---

    Goals, filters, schemas, and prompts live in YAML and files.
    [Concepts →](user-guide/concepts.md)

-   :material-source-branch: **Checkpoint & resume**

    ---

    Stage-by-stage runs with a SQLite ledger; continue after failures.
    [Running →](user-guide/running.md)

-   :material-database-export-outline: **Export for ingest**

    ---

    Merge successful extractions into one `database.json`.
    [Export format →](reference/export.md)

</div>

## Pipeline stages

LitCurate runs the following stages in order:

| # | Stage Name | Stage Keyword | CLI Keyword | Brief description |
|---|------------|---------------|-------------|-------------------|
| 1 | **Query Planning** | `query_generation` | `run-stage query_generation` | Uses the configured LLM to turn the research goal into focused literature-search queries. |
| 2 | **Literature Search** | `openalex_search` | `run-stage openalex_search` | Runs each query against OpenAlex and saves the raw paper results. |
| 3 | **Merge and Rank** | `merge_rank` | `run-stage merge_rank` | Combines results, removes duplicates, applies quality gates, and ranks candidate papers. |
| 4 | **Abstract Screening** | `filter_abstracts` | `run-stage filter_abstracts` | Uses the configured criteria and LLM to keep papers whose abstracts are relevant. |
| 5 | **PDF Download** | `download_pdfs` | `run-stage download_pdfs` | Finds and downloads available PDFs, recording success or failure for each paper. |
|  | <span class="optional-stage">↳ Manual PDF Import (Optional)</span> | <code class="optional-stage">ingest_pdfs</code> | <code class="optional-stage">ingest-pdfs</code> | <span class="optional-stage">Adds manually downloaded PDFs for papers missed by automatic download.</span> |
| 6 | **PDF-to-Markdown Conversion** | `convert_marker` | `run-stage convert_marker` | Converts downloaded PDFs into markdown with Marker. |
| 7 | **Markdown Cleanup** | `clean_markdown` | `run-stage clean_markdown` | Removes references and other configured noise, producing cleaner text for screening and extraction. |
| 8 | **Pre-Extraction Gate** | `pre_extract` | `run-stage pre_extract` | Applies inexpensive regex signals to skip papers that do not contain likely extraction targets. |
| 9 | **Full-Text Screening** | `filter_fulltext` | `run-stage filter_fulltext` | Screens cleaned full text with the configured criteria before extraction. |
| 10 | **Structured Extraction** | `extract_schema` | `run-stage extract_schema` | Extracts schema-shaped JSON from each eligible paper and validates the result. |
| 11 | **Database Export** | `export` | `run-stage export` | Merges successful per-paper extraction envelopes into `database.json`. |

Check the stages and their run status with:

```bash
litcurate stages
litcurate status <RUN_ID>
```

The status table shows each stage's current state (`pending`, `running`, `completed`,
`failed`, or `skipped`) and its primary artifact. See the complete
[stage reference](reference/stages.md) for inputs and outputs.

!!! tip "Missing PDFs after download"
    After `download_pdfs`, manually download missing papers and register them with
    `litcurate ingest-pdfs` before running `convert_marker`. See
    [Add missing PDFs manually](user-guide/running.md#optional-add-missing-pdfs-manually).

LitCurate is **domain-agnostic**. Science-specific vocabulary belongs in *your* schemas and prompts — not in the package core.

## Install

=== "macOS / Linux"

    ```bash
    git clone https://github.com/MineralsCloud/litcurate.git
    cd litcurate
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -U pip
    pip install -e ".[dev,openalex]"
    ```

=== "Windows"

    ```bash
    git clone https://github.com/MineralsCloud/litcurate.git
    cd litcurate
    python -m venv .venv
    .venv\Scripts\activate
    pip install -U pip
    pip install -e ".[dev,openalex]"
    ```

Smoke test (no API keys):

```bash
litcurate run configs/config.yaml
```

## Next steps

1. [Installation](user-guide/installation.md) — environment and extras  
2. [First steps](user-guide/first-steps.md) — secrets, config, first stage  
3. [CLI reference](reference/cli.md) — all commands  

---

<span id="license"></span>
**License:** MIT

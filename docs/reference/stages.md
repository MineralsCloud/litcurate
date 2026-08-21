# Stages

Stages run in fixed order. Display the configured stage list with:

```bash
litcurate stages
```

Display progress for a particular run with:

```bash
litcurate status <RUN_ID>
```

| # | Stage Name | Stage Keyword | CLI Keyword | Description | Primary artifact |
|---|------------|---------------|-------------|-------------|------------------|
| 1 | **Query Planning** | `query_generation` | `run-stage query_generation` | Turns the configured research goal into focused literature-search queries using an LLM. | `queries.json` |
| 2 | **Literature Search** | `openalex_search` | `run-stage openalex_search` | Searches OpenAlex for every generated query and preserves the raw results. | `openalex_raw/` |
| 3 | **Merge and Rank** | `merge_rank` | `run-stage merge_rank` | Merges query results, deduplicates papers, applies gates, and ranks candidates. | `papers_ranked.parquet` |
| 4 | **Abstract Screening** | `filter_abstracts` | `run-stage filter_abstracts` | Screens abstracts against the configured criteria and keeps relevant papers. | `papers_filtered.parquet` |
| 5 | **PDF Download** | `download_pdfs` | `run-stage download_pdfs` | Resolves PDF URLs through metadata APIs and downloads them with direct HTTP requests. It never opens or automates a browser. | `download_manifest.json` |
|  | <span class="optional-stage">↳ Manual PDF Import (Optional)</span> | <code class="optional-stage">ingest_pdfs</code> | <code class="optional-stage">ingest-pdfs</code> | <span class="optional-stage">Registers manually downloaded PDFs for papers missed by automatic download.</span> | <span class="optional-stage">Updates <code>download_manifest.json</code></span> |
| 6 | **PDF-to-Markdown Conversion** | `convert_marker` | `run-stage convert_marker` | Converts downloaded PDFs to markdown using Marker. | `convert_manifest.json` |
| 7 | **Markdown Cleanup** | `clean_markdown` | `run-stage clean_markdown` | Removes configured document noise and creates extraction-ready markdown. | `clean_manifest.json` |
| 8 | **Pre-Extraction Gate** | `pre_extract` | `run-stage pre_extract` | Uses regex signals as a fast, inexpensive gate before LLM screening and extraction. | `pre_extract_manifest.json` |
| 9 | **Full-Text Screening** | `filter_fulltext` | `run-stage filter_fulltext` | Keeps papers whose cleaned full text is likely to contain extractable evidence. | `fulltext_filter_manifest.json` |
| 10 | **Structured Extraction** | `extract_schema` | `run-stage extract_schema` | Extracts and validates schema-shaped JSON, retaining model and validation provenance. | `extract_manifest.json` |
| 11 | **Database Export** | `export` | `run-stage export` | Combines successful per-paper schema envelopes into one downstream-ready database. | `output/database.json` |

## Understanding `litcurate status`

The status command reads the run's SQLite ledger and reports:

- **Stage** — the stage identifier used by the CLI
- **Status** — `pending`, `running`, `completed`, `failed`, or `skipped`
- **Artifact** — the primary output written by that stage

## Optional operation after PDF download

**Manual PDF Import** is shown as a muted, optional sub-step below **PDF Download**, but
`ingest-pdfs` is a CLI operation rather than a ledger stage. It therefore does not
appear as a separate row in `litcurate status`. Use it between **PDF Download** and
**PDF-to-Markdown Conversion** when papers are missing:

```bash
litcurate ingest-pdfs --run-id <RUN_ID> --from-dir ~/manual_pdfs/ --dry-run
litcurate ingest-pdfs --run-id <RUN_ID> --from-dir ~/manual_pdfs/
```

This registers manually downloaded PDFs and updates the existing download manifest.
See [Add missing PDFs manually](../user-guide/running.md#optional-add-missing-pdfs-manually).

Artifact layout and resume behavior: [Artifacts & resume](artifacts.md).

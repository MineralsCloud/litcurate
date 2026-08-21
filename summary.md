# LitCurate — package summary

LitCurate is a **generic, config-driven literature-to-database pipeline**. It turns a research goal into structured JSON from peer-reviewed papers, with checkpointing and resume so long runs can stop and continue safely.

It is **not** tied to one science domain. Domain knowledge lives in YAML configs, JSON/YAML schemas, and prompt files. The same codebase can support materials, biomedicine, or any other extraction task you define.

---

## What it does

1. **Generate search queries** from a user goal (LLM)
2. **Search** the literature (OpenAlex)
3. **Rank and filter** papers (rules + optional LLM screening)
4. **Download PDFs** and convert them to markdown
5. **Extract** structured records into your schemas (LLM)
6. **Export** a single merged `database.json` for downstream ingest

Stages are independent CLI steps. You can run them one at a time, resume after failures, and re-run a single stage with `--force` when config changes.

---

## Design principles

| Idea | Meaning |
|------|---------|
| Config over code | Goals, filters, models, schemas, and prompts are YAML/files — no Python changes for a new domain |
| Checkpoint / resume | Per-run SQLite ledger + artifact manifests; finished work is not repeated |
| Schema-shaped output | Extractions follow declared schemas; results are wrapped with provenance (model, time, validation) |
| Provider-flexible LLMs | Anthropic and OpenAI-compatible endpoints (e.g. local Ollama) per stage |
| Export for ingest | Final artifact is `database.json`: all successful papers and their schema envelopes in one file |

---

## Who this is for

Teams that want a **reusable literature curation engine** as a dependency or sibling repo: clone LitCurate, install it, point a config at your schemas/prompts, and produce a database-ready JSON export. Experimental runs (specific topics, paper sets, or GPU servers) are **usage**, not part of the package identity.

---

## What ships in the package

- Python package `litcurate` + `litcurate` CLI
- Example configs, schemas, and prompts
- Tests and MIT license

Runtime outputs (`runs/`, PDFs, markdown, extractions) are **not** part of the package; they are created when you execute a pipeline.

---

## Typical integration

Another project (database UI, analysis notebook, domain app) should treat LitCurate as:

1. The **producer** of `database.json` (and optional per-paper extraction folders under a run)
2. A **tooling dependency** installed via `pip install -e .` (or from a published git tag)
3. Configured through **its own** YAML + schemas — not by hard-coding LitCurate internals

Downstream code should consume the exported JSON (or per-paper envelopes), not assume a particular scientific vocabulary beyond what that project’s schemas define.

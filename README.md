# LitCurate

[![CI](https://github.com/MineralsCloud/litcurate/actions/workflows/ci.yml/badge.svg)](https://github.com/MineralsCloud/litcurate/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/MineralsCloud/litcurate)](https://github.com/MineralsCloud/litcurate/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Config-driven pipeline that turns a research goal into a structured literature database.

**Docs:** [Documentation](https://mineralscloud.github.io/litcurate/)


**Flow:** search → filter → download PDFs → convert to markdown → extract JSON → export `database.json`

---

## Requirements

- Python **3.10+**
- API keys depending on your config (OpenAlex, Anthropic, and/or local Ollama)
- Optional: GPU for faster PDF→markdown conversion (Marker)

---

## Step 1 — Get the code

```bash
git clone https://github.com/MineralsCloud/litcurate.git
cd litcurate
```

Or, if you already have this folder:

```bash
cd litcurate
```

---

## Step 2 — Create a virtualenv and install

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows:

```bash
python -m venv .venv
.venv\Scripts\activate
```

Install LitCurate (editable) with OpenAlex support and test tools:

```bash
pip install -U pip
pip install -e ".[dev,openalex]"
```

Check that the CLI works:

```bash
litcurate --help
litcurate stages
```

Smoke test (**no API keys** — uses dry-run sample data):

```bash
litcurate run configs/config.yaml
```

---

## Step 3 — Configure secrets

Copy the example env file and edit it:

```bash
cp .env.example .env
```

Fill in at least:

| Variable | Needed for |
|----------|------------|
| `OPENALEX_API_KEY` and/or `OPENALEX_EMAIL` | Literature search |
| `UNPAYWALL_EMAIL` | Open-access PDF download |
| `ANTHROPIC_API_KEY` | Claude stages (if your config uses Anthropic) |
| `OPENAI_API_KEY` | Ollama / OpenAI-compatible APIs (any non-empty value for local Ollama) |

LitCurate loads `.env` automatically. Keys are **not** stored in YAML configs.

---

## Step 4 — Choose a config

`configs/config.yaml` is the shipped template and dry-run smoke test. Copy it for your domain and point `extraction.schemas` at your own files under `schemas/` and `prompts/`.

Set the config once per shell session:

```bash
export CONFIG=configs/config.yaml
```

---

## Step 5 — Local LLM screening (if your config uses Ollama)

Optional: screen abstracts/full text with a local OpenAI-compatible server (e.g. **Ollama**). Uncomment the `provider` / `base_url` / `model` fields under `abstract_filter` or `fulltext_filter` in your YAML.

```bash
# Install from https://ollama.com if needed
ollama pull qwen3:14b
ollama serve
```

Leave that running. In another terminal, keep the venv activated.

Remote GPU Ollama: set in YAML:

```yaml
base_url: http://GPU_HOST:11434/v1
```

---

## Step 6 — PDF conversion device

In your config, set Marker’s device:

```yaml
conversion:
  engine: marker
  device: cpu       # use cuda:0 on NVIDIA, or mps on Apple Silicon
```

---

## Step 7 — Run the pipeline (stage by stage)

Always activate the venv first:

```bash
cd litcurate
source .venv/bin/activate
export CONFIG=configs/config.yaml
```

### 7.1 Create a run (query generation)

```bash
litcurate run-stage query_generation --config $CONFIG
```

Copy the printed **run id**, then:

```bash
RUN_ID=<your_run_id>
# or: litcurate list-runs
```

Use the same `RUN_ID` for every later stage.

### 7.2 Search OpenAlex

```bash
litcurate run-stage openalex_search --run-id $RUN_ID
litcurate show openalex_search $RUN_ID
```

### 7.3 Merge and rank

```bash
litcurate run-stage merge_rank --run-id $RUN_ID
```

### 7.4 Filter abstracts (needs Ollama if configured)

```bash
litcurate run-stage filter_abstracts --run-id $RUN_ID --config $CONFIG
```

### 7.5 Download PDFs

```bash
litcurate run-stage download_pdfs --run-id $RUN_ID
```

This stage resolves PDF URLs through metadata services and downloads them over HTTP.
It does not install, open, or automate a browser.

### 7.6 Convert PDF → markdown (can be slow)

```bash
litcurate run-stage convert_marker --run-id $RUN_ID
```

Long server job:

```bash
mkdir -p runs/$RUN_ID/logs
nohup litcurate run-stage convert_marker --run-id $RUN_ID \
  > runs/$RUN_ID/logs/convert_marker.nohup.log 2>&1 &
tail -f runs/$RUN_ID/logs/convert_marker.nohup.log
```

### 7.7 Clean markdown

```bash
litcurate run-stage clean_markdown --run-id $RUN_ID
```

### 7.8 Pre-extract gate

```bash
litcurate run-stage pre_extract --run-id $RUN_ID
```

### 7.9 Fulltext filter (needs Ollama if configured)

```bash
litcurate run-stage filter_fulltext --run-id $RUN_ID --config $CONFIG
```

### 7.10 Extract structured JSON

```bash
litcurate run-stage extract_schema --run-id $RUN_ID --config $CONFIG
```

### 7.11 Export database

```bash
litcurate run-stage export --run-id $RUN_ID
```

Output:

```text
runs/<RUN_ID>/artifacts/output/database.json
```

This file merges successful per-paper extractions (full envelopes) ready for ingest.

---

## Everyday commands

```bash
litcurate list-runs
litcurate status $RUN_ID
litcurate show <stage_name> $RUN_ID
litcurate resume $RUN_ID
```

Re-run one stage after a config change:

```bash
litcurate run-stage filter_abstracts --run-id $RUN_ID --config $CONFIG --force
```

Pass `--config $CONFIG` on LLM stages so provider/model settings are applied (avoids a stale snapshot).

---

## Manual PDFs

If download fails (paywalled), name files by DOI with `/` → `_`:

| DOI | Filename |
|-----|----------|
| `10.1029/2011jb008988` | `10.1029_2011jb008988.pdf` |

```bash
litcurate ingest-pdfs --run-id $RUN_ID --from-dir ~/manual_pdfs/ --dry-run
litcurate ingest-pdfs --run-id $RUN_ID --from-dir ~/manual_pdfs/
litcurate run-stage convert_marker --run-id $RUN_ID --force
```

---

## Pipeline stages

| # | Stage | Typical needs |
|---|--------|----------------|
| 1 | `query_generation` | LLM (e.g. Anthropic) |
| 2 | `openalex_search` | OpenAlex |
| 3 | `merge_rank` | — |
| 4 | `filter_abstracts` | Ollama / LLM |
| 5 | `download_pdfs` | Unpaywall email |
| 6 | `convert_marker` | Marker (GPU optional) |
| 7 | `clean_markdown` | — |
| 8 | `pre_extract` | — |
| 9 | `filter_fulltext` | Ollama / LLM |
| 10 | `extract_schema` | LLM |
| 11 | `export` | — |

---

## Where files land

```text
runs/<RUN_ID>/
  run.db                 # SQLite status / resume
  config.snapshot.yaml   # frozen config for this run
  artifacts/             # queries, PDFs, markdown, extractions, output/
  logs/
```

---

## LLM providers in YAML

Per-stage override:

```yaml
extraction:
  provider: openai_compatible
  base_url: http://localhost:11434/v1
  model: qwen3:14b
```

Global default (required — no implicit Anthropic fallback):

```yaml
llm:
  provider: openai_compatible
  base_url: http://localhost:11434/v1
```

---

`marker-pdf` is included in the base install.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `litcurate: command not found` | Activate `.venv`, then `pip install -e ".[dev,openalex]"` |
| OpenAlex auth error | Set `OPENALEX_API_KEY` and/or `OPENALEX_EMAIL` in `.env` |
| Ollama connection error | Run `ollama serve` and `ollama pull qwen3:14b` |
| Marker / CUDA crash | Set `conversion.device: cpu` and re-run convert |
| Wrong model on a stage | Pass `--config $CONFIG` on that stage |
| Continue after a crash | `litcurate resume $RUN_ID` |

---

## Versioning and releases

LitCurate uses [Semantic Versioning](https://semver.org/). Git tags of the form `vX.Y.Z` publish a GitHub Release with source and wheel artifacts. See [CONTRIBUTING.md](CONTRIBUTING.md) for the full process.

## Citation

If you use LitCurate, please cite it via [CITATION.cff](CITATION.cff) (GitHub **Cite this repository**).

## License

MIT — see [LICENSE](LICENSE).

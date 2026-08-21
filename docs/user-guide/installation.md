# Installation

## Requirements

- Python **3.10** or newer
- Network access for literature APIs (OpenAlex, Unpaywall) when not in dry-run
- Optional: [Ollama](https://ollama.com) or another OpenAI-compatible LLM server
- Optional: NVIDIA GPU / Apple MPS for faster PDF → markdown (Marker)

## Create a virtual environment

=== "macOS / Linux"

    ```bash
    git clone https://github.com/MineralsCloud/litcurate.git
    cd litcurate
    python3 -m venv .venv
    source .venv/bin/activate
    ```

=== "Windows"

    ```bash
    git clone https://github.com/MineralsCloud/litcurate.git
    cd litcurate
    python -m venv .venv
    .venv\Scripts\activate
    ```

## Install LitCurate

```bash
pip install -U pip
pip install -e ".[dev,openalex]"
```

| Extra | Purpose |
|-------|---------|
| `openalex` | OpenAlex client (`pyalex`) |
| `dev` | `pytest`, `ruff` |
| `docs` | MkDocs Material (this site) |

Verify:

```bash
litcurate --help
litcurate stages
```

## Optional: local LLM (Ollama)

```bash
ollama pull qwen3:14b
ollama serve
```

Set `OPENAI_API_KEY` to any non-empty value in `.env` (for example `ollama`). Configure `provider` / `base_url` / `model` in your YAML — see [LLM providers](../reference/llm.md).

## Check the dry-run

```bash
litcurate run configs/config.yaml
```

!!! success "Expected"
    The pipeline completes using sample payloads when `dry_run: true` in the config. No API keys required for this smoke test.

To run the real pipeline, open `configs/config.yaml` and change:

```yaml
dry_run: false
```

Then run the same command:

```bash
litcurate run configs/config.yaml
```

With `dry_run: false`, LitCurate performs live searches, network downloads, and
configured LLM calls. Set the required environment variables before running.

Next: [First steps](first-steps.md).

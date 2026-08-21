# First steps

## 1. Configure secrets

```bash
cp .env.example .env
```

Edit `.env`. Keys are loaded automatically and must **not** be placed in YAML.

| Variable | Needed for |
|----------|------------|
| `OPENALEX_API_KEY` and/or `OPENALEX_EMAIL` | Literature search |
| `UNPAYWALL_EMAIL` | Open-access PDF download |
| `ANTHROPIC_API_KEY` | Claude stages (if configured) |
| `OPENAI_API_KEY` | Ollama / OpenAI-compatible APIs |

Full list: [Environment variables](../reference/environment.md).

## 2. Choose a config

`configs/config.yaml` is the shipped generic template. It uses the example extraction
schema and prompt documented in [Schemas & prompts](../reference/schemas.md):

- `schemas/example/record.json`
- `prompts/example/prompt.md`

The complete file is documented in
[Configuration](../reference/configuration.md#full-configuration-example).

```bash
export CONFIG=configs/config.yaml
```

Edit `user_goal`, filters, and `extraction.schemas` as needed. See [Configuration](../reference/configuration.md).

## 3. Set the PDF converter device

```yaml
conversion:
  engine: marker
  device: cpu       # cuda:0 on NVIDIA, mps on Apple Silicon
```

## 4. Create a run

```bash
export CONFIG=configs/config.yaml
litcurate run-stage query_generation --config $CONFIG
```

Copy the printed run id:

```bash
RUN_ID=<your_run_id>
```

!!! tip
    List recent runs anytime with `litcurate list-runs`.

## 5. Continue stage by stage

Use the same `RUN_ID` for later stages. Full sequence: [Running a pipeline](running.md).

```bash
litcurate run-stage openalex_search --run-id $RUN_ID
litcurate status $RUN_ID
```

Pass `--config $CONFIG` on LLM stages so provider settings apply.

## 6. Export

When extraction is done:

```bash
litcurate run-stage export --run-id $RUN_ID
```

Output:

```text
runs/<RUN_ID>/artifacts/output/database.json
```

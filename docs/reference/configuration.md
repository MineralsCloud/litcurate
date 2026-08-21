# Configuration

Pipeline behavior is controlled by a YAML file.

| File | Role |
|------|------|
| [`configs/config.yaml`](https://github.com/MineralsCloud/litcurate/blob/main/configs/config.yaml) | Complete generic template and dry-run smoke test |

```bash
export CONFIG=configs/config.yaml
```

## Top-level sections

| Section | Purpose |
|---------|---------|
| `run` | Run name and `user_goal` |
| `llm` | Required global LLM fallback (`provider` must be set; stages inherit when they omit overrides) |
| `search` | Query generation and OpenAlex settings |
| `abstract_filter` | Abstract screening criteria / model |
| `download` | PDF download options |
| `conversion` | Marker device (`cpu` / `cuda:0` / `mps`) |
| `markdown_clean` | Strip back-matter (references, acknowledgments, funding, optional supplementary) |
| `pre_extract` | Regex gate before extraction |
| `fulltext_filter` | Full-text screening |
| `extraction` | Schemas, prompts, models, and `section_mode` |
| `dry_run` | If `true`, use sample payloads (no live LLM extract) |

The `download` stage uses metadata APIs and direct HTTP requests only. LitCurate does
not install, launch, or automate a web browser.

## Conversion device

```yaml
conversion:
  engine: marker
  device: cpu       # or cuda:0 / mps
```

## Extraction section mode

`extract_schema` chooses which markdown file to send to the model:

| `extraction.section_mode` | Source | Behavior |
|---------------------------|--------|----------|
| `cleaned_markdown` | `artifacts/markdown_clean/` | Send the cleaned paper after `strip_*` rules |
| `full_document` | `artifacts/markdown/` | Send Marker output **without** stripping |

```yaml
extraction:
  section_mode: cleaned_markdown   # or full_document
```

!!! tip "Default: `cleaned_markdown`"
    Use this when you want references / acknowledgments / funding removed before
    extraction. Set `full_document` only if you need the unstripped Marker markdown
    (including back-matter that `markdown_clean` would normally remove).

## Full configuration example

The complete shipped config below includes the available pipeline settings. Copy it
and adapt the research goal, filters, models, schemas, prompts, and hardware settings
for your domain.

Supporting files:

- `schemas/example/record.yaml`
- `schemas/example/source.json`
- `schemas/example/source.yaml` (equivalent YAML alternative)
- `prompts/example/prompt.md`

```yaml title="configs/config.yaml"
--8<-- "configs/config.yaml"
```

!!! tip "Adapt for your domain"
    Copy this file, replace `user_goal` / filter criteria / schemas / prompts, and keep
    the same section structure. See [Custom domains](../user-guide/custom-domains.md).

Related: [Schemas & prompts](schemas.md), [LLM providers](llm.md).

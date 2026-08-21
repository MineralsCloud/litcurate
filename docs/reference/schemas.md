# Schemas and prompts

Extraction is driven by **schema + prompt** pairs under `extraction.schemas`.
LitCurate ships worked examples you can copy and adapt.

## Shipped examples

| Role | Path |
|------|------|
| Example schema (JSON Schema) | [`schemas/example/record.json`](https://github.com/MineralsCloud/litcurate/blob/main/schemas/example/record.json) |
| Example schema (declarative YAML) | [`schemas/example/record.yaml`](https://github.com/MineralsCloud/litcurate/blob/main/schemas/example/record.yaml) |
| Example prompt | [`prompts/example/prompt.md`](https://github.com/MineralsCloud/litcurate/blob/main/prompts/example/prompt.md) |
| Bibliographic source schema (JSON) | [`schemas/example/source.json`](https://github.com/MineralsCloud/litcurate/blob/main/schemas/example/source.json) |
| Bibliographic source schema (YAML) | [`schemas/example/source.yaml`](https://github.com/MineralsCloud/litcurate/blob/main/schemas/example/source.yaml) |

The default dry-run config wires the example record schema:

```yaml
extraction:
  schemas:
    - name: record
      path: schemas/example/record.json
      prompt: prompts/example/prompt.md
      version: "2.1"
      empty_list_field: eos_entries
```

!!! note "Why EOS fields?"
    The example schema is a concrete equation-of-state extraction shape (`eos_entries`
    with V0 / K0 / Kp). Treat it as a **template for list-shaped scientific records**,
    not a package dependency on mineral physics. See the
    [full configuration example](configuration.md#full-configuration-example) for
    how schemas and prompts are connected.

## Example prompt

```markdown title="prompts/example/prompt.md"
--8<-- "prompts/example/prompt.md"
```

## Example schema

Choose either JSON Schema or declarative YAML — same extraction shape, different
file formats. Do not configure both in the same `extraction.schemas` list.

=== "JSON Schema"

    ```yaml
    - name: record
      path: schemas/example/record.json
      prompt: prompts/example/prompt.md
      version: "2.1"
      empty_list_field: eos_entries
    ```

    ```json title="schemas/example/record.json"
    --8<-- "schemas/example/record.json"
    ```

=== "Declarative YAML"

    ```yaml
    - name: record
      format: declarative_yaml
      path: schemas/example/record.yaml
      prompt: prompts/example/prompt.md
      version: "2.1"
      empty_list_field: eos_entries
    ```

    ```yaml title="schemas/example/record.yaml"
    --8<-- "schemas/example/record.yaml"
    ```

!!! warning
    Do not configure both record schemas in the same extraction list. They represent
    the same schema in two file formats; choose either JSON or YAML.

### Valid payload shape

Top-level object with an `eos_entries` array. Each entry requires at least
`phase`, `eos_model`, and `evidence`:

```json
{
  "eos_entries": [
    {
      "phase": "ExamplePhase",
      "composition": "ABO3",
      "eos_model": "3rd-order Birch-Murnaghan",
      "method": "XRD",
      "V0": "46.23",
      "V0_unit": "Å^3",
      "V0_determination": "measured",
      "K0": "106 (2)",
      "K0_unit": "GPa",
      "K0_determination": "fitted",
      "Kp": "4",
      "Kp_determination": "fixed",
      "origin": "this_study",
      "evidence": "Table 2 reports K0 = 106 (2) GPa with K′ fixed at 4."
    }
  ]
}
```

If the paper has nothing extractable, return `{ "eos_entries": [] }`.

## Optional source schema

Bibliographic `source` metadata is filled from OpenAlex / parquet, **not extracted by
an LLM**. Set `fill_from: papers_meta`; do not provide a prompt:

```yaml
extraction:
  schemas:
    - name: record
      path: schemas/example/record.json
      prompt: prompts/example/prompt.md
      empty_list_field: eos_entries
    - name: source
      path: schemas/example/source.json
      fill_from: papers_meta
      skip_when_prior_empty: record
```

With `fill_from` set:

1. LitCurate reads bibliographic fields from the best available paper metadata
   (`papers_filtered.parquet`, then `papers_ranked.parquet`).
2. It does **not** call an LLM and does **not** read a prompt.
3. It validates the generated payload against the configured source schema.
4. It writes the normal extraction envelope as `<paper_id>/source.json`.

The schema is therefore required even though a prompt is not.

=== "JSON Schema"

    ```yaml
    - name: source
      path: schemas/example/source.json
      fill_from: papers_meta
    ```

    ```json title="schemas/example/source.json"
    --8<-- "schemas/example/source.json"
    ```

=== "YAML Schema"

    ```yaml
    - name: source
      format: yaml_schema
      path: schemas/example/source.yaml
      fill_from: papers_meta
    ```

    ```yaml title="schemas/example/source.yaml"
    --8<-- "schemas/example/source.yaml"
    ```

!!! warning
    Do not configure both source schemas in the same extraction list. They represent
    the same schema in two file formats; choose either JSON or YAML.

There is intentionally no source prompt because this workflow does
not use an LLM for source metadata.

```json title="Example source payload"
{
  "doi": "10.1000/example",
  "title": "Example paper",
  "authors": ["A. Author", "B. Author"],
  "journal": "Example Journal",
  "year": 2026,
  "source_type": "journal",
  "evidence_text": "Bibliographic metadata supplied by the paper index.",
  "confidence": 1.0
}
```

## Schema entry fields

```yaml
extraction:
  schemas:
    - name: record
      path: schemas/example/record.json
      prompt: prompts/example/prompt.md
      version: "2.1"
      empty_list_field: eos_entries
```

| Field | Meaning |
|-------|---------|
| `name` | Schema id; output filename stem |
| `path` | JSON Schema, declarative YAML, or related format |
| `prompt` | Instructions for the LLM (required unless `fill_from` is set) |
| `format` | `json_schema` (default), `yaml_schema`, `declarative_yaml`, or `pydantic` |
| `version` | Optional schema version recorded in envelopes |
| `fill_from` | e.g. `papers_meta` — fill from paper metadata instead of calling an LLM |
| `skip_when_prior_empty` | Skip if a prior schema’s `empty_list_field` is empty |
| `empty_list_field` | List field used for empty checks / export counts |

## Declarative YAML format

`format: declarative_yaml` is a shorter authoring style (`string`, `string?`,
`enum(...)`, nested `fields` / `array`). The example record schema above shows the
full file; configure it with:

```yaml
- name: record
  format: declarative_yaml
  path: schemas/example/record.yaml
  prompt: prompts/example/prompt.md
  empty_list_field: eos_entries
```

## Output location

```text
runs/<RUN_ID>/artifacts/extractions/<paper_id>/<schema_name>.json
```

Each file is an **envelope** (metadata + `payload`). See [Export format](export.md).

## Adapting for your domain

1. Copy `schemas/example/record.json` → `schemas/my_domain/...`
2. Copy `prompts/example/prompt.md` → `prompts/my_domain/...`
3. Rename fields / instructions to match what you extract
4. Point `extraction.schemas` at the new paths
5. Keep `empty_list_field` aligned with your top-level list property

See [Custom domains](../user-guide/custom-domains.md).

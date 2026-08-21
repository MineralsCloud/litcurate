# Custom domains

LitCurate does not hard-code a scientific domain. Start from the shipped template:

| Starting point | When to use |
|----------------|-------------|
| `configs/config.yaml` + `schemas/example/record.json` + `prompts/example/prompt.md` | Complete template and dry-run starting point |

The example record schema is a concrete list extraction (EOS V0/K0/Kp). Use it as a
pattern for any domain that extracts repeated structured rows from papers.

To support a new topic:

1. Copy `configs/config.yaml` → e.g. `configs/my_domain.yaml`
2. Write the research `user_goal` and filter criteria
3. Copy `schemas/example/record.json` → `schemas/my_domain/` and adapt fields
4. Copy `prompts/example/prompt.md` → `prompts/my_domain/` and adapt instructions
5. Point `extraction.schemas` at those files (`empty_list_field` must match your list key)
6. Set LLM providers for search / filter / extract as needed
7. Run with `export CONFIG=configs/my_domain.yaml`

No Python changes are required for most new domains.

## Downstream projects

```text
LitCurate (this package)
    → runs/<id>/artifacts/output/database.json
        → Your app / DB / notebook
```

Keep experimental campaigns and large domain corpora **outside** the package repository when you publish LitCurate itself.

See also: [Schemas & prompts](../reference/schemas.md), [Export format](../reference/export.md).

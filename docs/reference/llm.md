# LLM providers

LitCurate supports two backends. You choose them with `provider` on the global
`llm:` block or on each LLM stage (`search`, `abstract_filter`,
`fulltext_filter`, `extraction`).

| Provider | Use for | Auth |
|----------|---------|------|
| `anthropic` | Claude models (Anthropic API) | `ANTHROPIC_API_KEY` |
| `openai_compatible` | Any OpenAI-style Chat Completions API | `OPENAI_API_KEY` (or a custom env via `api_key_env`) |

Always set an explicit `model:` on every LLM stage. For
`openai_compatible`, also set `base_url`.

!!! important "Global `llm:` is a required fallback"
    Every config must include a global `llm:` block with
    `provider: anthropic` or `provider: openai_compatible`. There is no implicit
    default. Config load fails if it is missing.

    Stages that set their own `provider` / `base_url` / `api_key_env` ignore the
    matching global fields. Stages that omit those fields **fall back** to the
    global `llm:` values.

## How resolution works

1. Start from the required global `llm:` block (the fallback).
2. Overlay any per-stage `provider`, `base_url`, `api_key_env`, or `timeout_seconds`.
3. Use that stage’s own `model:` string when calling the API.

Example: if `abstract_filter` sets `provider: openai_compatible` and `base_url`, it
uses those. If `search` only sets `model:` and no `provider`, it falls back to
global `llm.provider`.

You can mix backends in one config — for example Anthropic for query generation
and a local or cloud OpenAI-compatible model for screening.

## Anthropic (Claude)

```yaml
search:
  provider: anthropic
  model: claude-sonnet-4-6
```

```bash
# .env
ANTHROPIC_API_KEY=sk-ant-...
```

Omit `base_url` for Anthropic. LitCurate uses the official Anthropic SDK.

## OpenAI-compatible APIs

`openai_compatible` posts to `{base_url}/chat/completions`. That covers OpenAI,
DeepSeek, Grok (xAI), Ollama, vLLM, and most cloud proxies.

| Service | Example `base_url` | Example `model` | Key |
|---------|--------------------|-----------------|-----|
| OpenAI | `https://api.openai.com/v1` | `gpt-4.1` | Real OpenAI key |
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` | DeepSeek key |
| Grok (xAI) | `https://api.x.ai/v1` | `grok-3` | xAI key |
| Ollama (local) | `http://localhost:11434/v1` | `qwen3:14b` | Any non-empty value |
| vLLM / proxy | `http://HOST:PORT/v1` | Host-specific id | Host-specific |

Use the exact model id your host documents. LitCurate does not rename models.

=== "OpenAI"

    ```yaml
    extraction:
      provider: openai_compatible
      base_url: https://api.openai.com/v1
      model: gpt-4.1
    ```

    ```bash
    # .env
    OPENAI_API_KEY=sk-...
    ```

=== "DeepSeek"

    ```yaml
    extraction:
      provider: openai_compatible
      base_url: https://api.deepseek.com/v1
      model: deepseek-chat
    ```

    ```bash
    # .env — store the DeepSeek key under OPENAI_API_KEY, or rename with api_key_env
    OPENAI_API_KEY=sk-...
    ```

=== "Grok (xAI)"

    ```yaml
    extraction:
      provider: openai_compatible
      base_url: https://api.x.ai/v1
      model: grok-3
    ```

    ```bash
    # .env
    OPENAI_API_KEY=xai-...
    ```

=== "Ollama"

    ```bash
    ollama pull qwen3:14b
    ollama serve
    ```

    ```yaml
    abstract_filter:
      provider: openai_compatible
      base_url: http://localhost:11434/v1   # or http://GPU_HOST:11434/v1
      model: qwen3:14b
    ```

    ```bash
    # .env — any non-empty value is fine for local Ollama
    OPENAI_API_KEY=ollama
    ```

## Custom API key env name

By default, `openai_compatible` reads `OPENAI_API_KEY`. To keep keys separate:

```yaml
extraction:
  provider: openai_compatible
  base_url: https://api.deepseek.com/v1
  model: deepseek-chat
  api_key_env: DEEPSEEK_API_KEY
```

```bash
# .env
DEEPSEEK_API_KEY=sk-...
```

## Global fallback (required)

Every config must declare a global `llm:` block. There is no implicit provider.

```yaml
llm:
  provider: openai_compatible   # or anthropic
  base_url: http://localhost:11434/v1
```

This is the **fallback** for stages that omit `provider` / `base_url` /
`api_key_env`. A stage can still override with its own `provider` and `model`.

## Mixed example

```yaml
llm:
  provider: openai_compatible
  base_url: http://localhost:11434/v1

search:
  provider: anthropic
  model: claude-sonnet-4-6

abstract_filter:
  provider: openai_compatible
  base_url: http://localhost:11434/v1
  model: qwen3:14b

extraction:
  provider: openai_compatible
  base_url: https://api.openai.com/v1
  model: gpt-4.1
```

Related: [Environment variables](environment.md), [Configuration](configuration.md).

# Environment variables

Copy `.env.example` to `.env`. LitCurate loads `.env` automatically.

!!! warning
    Do not put API keys in YAML configs.

| Variable | Used for |
|----------|----------|
| `OPENALEX_API_KEY` | OpenAlex search (recommended) |
| `OPENALEX_EMAIL` | OpenAlex polite pool if no key |
| `UNPAYWALL_EMAIL` | Open-access PDF lookup |
| `ANTHROPIC_API_KEY` | Claude stages (`provider: anthropic`) |
| `OPENAI_API_KEY` | OpenAI-compatible APIs (OpenAI, DeepSeek, Grok, Ollama, …) |
| *(custom)* | Any name set via stage `api_key_env` |

```bash
OPENALEX_API_KEY=
OPENALEX_EMAIL=you@university.edu
UNPAYWALL_EMAIL=you@university.edu
ANTHROPIC_API_KEY=
OPENAI_API_KEY=ollama
```

# Troubleshooting

| Problem | Fix |
|---------|-----|
| `litcurate: command not found` | Activate `.venv`, then `pip install -e ".[dev,openalex]"` |
| OpenAlex auth error | Set `OPENALEX_API_KEY` and/or `OPENALEX_EMAIL` in `.env` |
| Ollama connection error | Run `ollama serve` and pull your model |
| Marker / CUDA crash | Set `conversion.device: cpu` and re-run convert |
| Wrong model on a stage | Pass `--config $CONFIG` on that stage |
| Continue after a crash | `litcurate resume $RUN_ID` |
| Stale paths after moving a run | `litcurate normalize-manifests --run-id $RUN_ID` |

!!! tip
    Use `litcurate status $RUN_ID` and `litcurate show <stage> $RUN_ID` to inspect progress without re-running.

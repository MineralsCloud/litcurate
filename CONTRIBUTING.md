# Contributing

## Development setup

```bash
git clone https://github.com/MineralsCloud/litcurate.git
cd litcurate
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e ".[dev,openalex]"
```

Run the test suite and linter before opening a pull request:

```bash
pytest
ruff check src tests
```

Smoke test (no API keys):

```bash
litcurate run configs/config.yaml
```

User-facing changes belong in `CHANGELOG.md` under **Unreleased**.

## Versioning

This project follows [Semantic Versioning](https://semver.org/):

| Increment | When |
|-----------|------|
| **MAJOR** (`1.0.0`) | Breaking CLI, config, or Python API changes |
| **MINOR** (`0.2.0`) | Backward-compatible features |
| **PATCH** (`0.1.1`) | Backward-compatible bug fixes |

The package version lives in `src/litcurate/__init__.py` (`__version__`). Hatch reads it at build time.

## Cutting a release

1. CI on `main` is green.
2. Move items from **Unreleased** in `CHANGELOG.md` into a new `## [X.Y.Z] - YYYY-MM-DD` section and update the compare links at the bottom.
3. Set `__version__ = "X.Y.Z"` in `src/litcurate/__init__.py`.
4. Commit on `main`:

   ```bash
   git add CHANGELOG.md src/litcurate/__init__.py
   git commit -m "Release vX.Y.Z"
   git push origin main
   ```

5. Tag and push the tag (this publishes the GitHub Release and attaches `sdist` / wheel artifacts):

   ```bash
   git tag -a vX.Y.Z -m "vX.Y.Z"
   git push origin vX.Y.Z
   ```

Do not retag a published version. If a release needs a fix, cut `X.Y.Z+1`.

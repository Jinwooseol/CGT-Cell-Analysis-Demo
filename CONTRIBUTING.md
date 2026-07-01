# Contributing

Thanks for taking a look! This repository is a portfolio project, but it is set up like a real one
and welcomes the same workflow.

## Getting set up

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev,ai]"
pre-commit install                 # optional, runs ruff on commit
```

## Development workflow

1. Create a branch off `main`.
2. Make your change, keeping the layer boundaries (UI → controller → workers → io/model).
3. Run the checks below until they're green.
4. Open a pull request describing the change and how you verified it.

## Quality gates

| Check | Command |
|-------|---------|
| Lint | `ruff check cgt_cell_analysis_demo tests` |
| Format | `ruff format cgt_cell_analysis_demo tests` |
| Tests | `pytest` (use `QT_QPA_PLATFORM=offscreen` on headless machines) |

CI (GitHub Actions) runs lint + tests on Python 3.10, 3.11, and 3.12. Please make sure the suite
passes locally before pushing.

## Conventions

- **Language:** code, comments, and docs are in English.
- **Style:** enforced by `ruff` (see `[tool.ruff]` in `pyproject.toml`). Don't hand-format; run
  `ruff format`.
- **Logging:** workers emit human-readable strings through Qt signals using `log_format(...)`.
  Headless/library code uses the standard `logging` module via `get_logger(...)`.
- **Tests:** add or update tests under `tests/` for any behavioural change. Keep them fast and
  deterministic (no network, no GPU requirement, no real datasets).
- **Configuration:** new options go on `AppConfig` in `config.py` with a sensible default and, where
  relevant, a validation rule.

## Project layout

See [`docs/architecture.md`](docs/architecture.md) for the layer responsibilities and data flow.

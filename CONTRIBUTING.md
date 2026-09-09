# Contributing

This project is developed in small, tested milestones so that each change remains reviewable and
explainable.

## Development setup

```bash
uv sync --locked --extra dev
uv run entity-resolution-engine doctor
```

## Before opening a pull request

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src tests
uv run pytest
```

## Change discipline

- Keep one concern per pull request.
- Add tests for new behavior and regressions.
- Document material architecture or threshold decisions in `docs/decisions/`.
- State the dataset, seed, command, and environment behind every reported metric.
- Do not commit real personal data, credentials, generated reports, or local environments.

Commit messages use a short imperative subject, for example:

```text
Add deterministic CPF normalization
Reject ambiguous duplicate identifiers
Measure candidate blocking recall
```

# Contributing

Keep each change focused on one problem so its behavior and test results can be reviewed
together. Code, identifiers, docstrings, commit messages, and repository documentation use English.

## Development setup

```bash
uv sync --locked --extra dev
uv run entity-resolution-engine doctor
```

Without `uv`, create a virtual environment and install the development tools:

```bash
python -m venv .venv
python -m pip install --editable ".[dev]"
```

## Required checks

Run all four checks before each commit:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src tests
uv run pytest
```

## Matching changes

- Add or update tests for changed behavior and reproduced bugs.
- Retain component scores, reasons, and applied thresholds for automatic decisions.
- Keep an explicit review outcome when evidence is uncertain.
- Compare a proposed model against the transparent baseline before adopting it.
- Explain the reason for a new dependency or architectural layer.
- Document material architecture or threshold decisions in `docs/decisions/`.

## Data and evaluation

Use only synthetic data generated with a fixed seed. Do not commit real personal information,
employer records, internal system names, record layouts, operating procedures, credentials, or
local environments. Generated reports belong under the ignored `reports/` directory.

Every published metric needs a reproducible dataset, seed, command, and output artifact.
Distinguish matching accuracy from test coverage and synthetic results from real-world validation.

## Scope

The released application is a local CLI. A web interface, cloud deployment, distributed
processing, Kubernetes, and LLM-based matching are outside this release.

Keep one concern per pull request and use a short imperative commit subject, for example:

```text
Reject ambiguous duplicate identifiers
Measure candidate blocking recall
```

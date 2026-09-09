# Repository working agreement

## Purpose

Build a portfolio-quality entity resolution engine through small, explainable increments. The
repository must demonstrate sound software and data engineering, not merely accumulate features.

## Non-negotiable rules

- Write code, identifiers, docstrings, commits, and repository documentation in English.
- Use only synthetic data generated with a fixed seed. Never use employer data or real PII.
- Do not mention internal employer systems, record layouts, or operating procedures.
- Keep every automatic decision auditable: retain component scores, reasons, and thresholds.
- Preserve an explicit review/abstention outcome for uncertain pairs.
- Never publish a metric without a reproducible dataset, command, and output artifact.
- Add or update tests with every behavioral change.
- Explain the reason before adding a dependency or architectural layer.
- Prefer a transparent baseline over an opaque model unless evaluation proves the benefit.
- Keep commits small enough that their intent can be explained in a technical interview.

## Quality gate

Run before every commit:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src tests
uv run pytest
```

## Scope control

The first stable release is a local CLI. A web interface, cloud deployment, distributed compute,
Kubernetes, and LLM-based matching are outside the initial scope.

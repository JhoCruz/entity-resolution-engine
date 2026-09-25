# v1.0.0: local entity resolution workflow

The first stable command-line workflow reads two CSV or XLSX sources, checks source contracts,
normalizes mapped fields, selects bounded candidate pairs, and writes a reduced report plus an
optional local full audit. Exact identifiers can establish automatic matches only with
independent support and no conflicting evidence. Approximate name and date candidates stay in
review by default. The optional synthetic policy demonstrates threshold selection on a labeled
tuning split and reports held-out results; it is **not** validated for real-world identities.

## Start here

```bash
uv sync --locked --extra dev
uv run entity-resolution-engine doctor
uv run entity-resolution-engine reconcile --config examples/basic-job.toml \
  --output reports/first-run
uv run entity-resolution-engine reconcile --config examples/name-variants-job.toml \
  --output reports/name-variants
```

Outputs default to per-run references with no names, identifiers, or normalized personal values.
Add `--full-audit` to a new output directory only when the original and normalized data are
needed locally. See [report details](REPORTS.md) and the [configuration guide](CONFIGURATION.md).

## Reproduce the evidence

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src tests
uv run pytest
uv run python scripts/evaluate_benchmark.py --output docs/evaluation/baseline.json
uv run python scripts/calibrate_policy.py --output docs/evaluation/synthetic-policy.json
uv run python scripts/benchmark_performance.py --output docs/evaluation/performance.json
```

The first two evaluation artifacts are deterministic. The last uses reproducible synthetic
inputs but machine-dependent timings. See [evaluation](EVALUATION.md), [calibration](CALIBRATION.md),
and [performance](PERFORMANCE.md) for denominators and limitations. CI also builds the Python
package and container and exercises the container entry point.

## Limits

- The benchmark uses invented Brazilian-style records; it does not estimate accuracy on real data.
- The default local workflow intentionally sends approximate suggestions to review.
- Opaque references in reduced reports are pseudonyms, not a legal anonymity guarantee.
- Candidate caps keep comparisons bounded and may require a more selective strategy for large
  or highly repeated datasets.
- The tool does not host data or provide a web UI.

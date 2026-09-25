# Data policy

Only reproducible synthetic data belongs in this repository.

The benchmark generator uses a curated Brazilian-style pool, a fixed random seed, and controlled
corruptions. It emits two source tables and a separate file with hidden entity keys and known
true pairs. This avoids an extra dependency and guarantees every identifier is invented. See
[`docs/EVALUATION.md`](../docs/EVALUATION.md) for regeneration and metric definitions.

Never add:

- employer or institutional data;
- real names, identifiers, addresses, phone numbers, or e-mail addresses;
- internal schemas, screenshots, exports, or procedure descriptions;
- raw files received from another person without an explicit redistribution license.

Large generated datasets and local outputs are ignored by Git. Small deterministic fixtures used
by automated tests may be committed under `tests/fixtures/` when they contain no real PII.

The documented CLI example uses the small files under `examples/data/`. They contain invented
entities generated with seed `20260920`. Regenerate them with:

```bash
uv run python scripts/generate_example_data.py
```

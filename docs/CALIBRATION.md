# Synthetic demonstration policy

The default `reconcile` command holds every approximate name or date pair for review. To
demonstrate a separately validated decision policy, regenerate the committed artifact:

```bash
uv run python scripts/calibrate_policy.py --output docs/evaluation/synthetic-policy.json
```

The tuning step uses only the `tuning` synthetic split and its hidden pair labels. It tries a
small fixed grid of automatic-match thresholds, chooses the first that produces **zero false
matches on tuning labels**, and sets the review threshold low enough to retain every observed
true selected pair for review. It then applies the chosen policy once to a separately seeded
`final` split and records both results in the JSON artifact. This is a demonstration: zero
observed errors in a small synthetic sample does not establish a real-world error rate.

To use that artifact deliberately on the matching generated example configuration:

```bash
uv run python scripts/generate_benchmark.py --output-directory benchmarks/final --seed 20260925
uv run entity-resolution-engine reconcile --config benchmarks/final/job.toml \
  --output reports/final-calibrated --calibration docs/evaluation/synthetic-policy.json
```

The CLI checks that field names, semantic types, and weights match the calibration. The output
records the active thresholds and `synthetic_tuning_only` provenance. The default command remains
review-only even when the policy file exists. Real input distributions may differ; do not use this
synthetic policy to justify automatic matches on real people. Collect permitted labeled data and
validate a separate policy for the intended workflow before enabling automatic fuzzy decisions.

## Safety constraints, even in the demo

- Only a name-based candidate with a valid, independent exact supporting field can be accepted.
- An identifier conflict, another structured-field conflict, or invalid input blocks an automatic
  match regardless of score.
- Any competing selected pair sharing either row blocks an automatic match. Exact review pairs
  count as competitors; a date-only candidate always stays in review.
- A name candidate with a valid score below the tuned review threshold may be marked `no_match`.
  Conflicting and invalid fields remain in review. Unselected pairs remain unresolved.
- Exact-identifier matches continue to use their documented strict rules.

On the final 80-entity synthetic split, the default baseline accepts 23 of 63 true pairs.
The explicit demonstration policy accepts 30, with no observed false match in this small test;
33 true pairs remain for review. Read the full reproducible [policy artifact](evaluation/synthetic-policy.json)
and [evaluation notes](EVALUATION.md) before drawing conclusions.

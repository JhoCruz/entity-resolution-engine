# Reproducible synthetic benchmark

Regenerate two independent synthetic splits and compare the baseline with their separate ground
truth:

```bash
uv run python scripts/evaluate_benchmark.py --output docs/evaluation/baseline.json
```

The committed output at [`evaluation/baseline.json`](evaluation/baseline.json) is byte-for-byte
reproducible with that command and checked in tests. Each split has 80 invented people, a different
fixed seed, and a separate `labels.csv` that is **never** passed to the engine. The CSV inputs use
invented `SYN-` identifiers rather than real document numbers. To inspect one split directly:

```bash
uv run python scripts/generate_benchmark.py --output-directory benchmarks/final \
  --seed 20260925 --size 80
uv run entity-resolution-engine reconcile --config benchmarks/final/job.toml \
  --output reports/benchmark-final
```

Generated input files under `benchmarks/` and local reports under `reports/` are ignored by Git.
The generator uses a curated Brazilian-style name pool and Python's seeded random generator,
avoiding an extra library dependency. It samples cases with identical values, identifier
formatting changes, transposed letters, missing or conflicting identifiers, altered dates, a pair
whose two name anchors are changed, and entities absent on the right. Some unrelated right records
have similar names; a few harder unrelated records also share the left record's birth date and
have no identifier. This test covers only these invented conditions; it cannot establish accuracy
on production data or every regional naming pattern.

## Reading the numbers

| Metric | Definition |
| --- | --- |
| Blocking recall | True pairs selected by an exact ID, name key, or date key divided by all true pairs. |
| Precision | Correct automatic matches divided by all automatic matches; zero if none. |
| Recall | Correct automatic matches divided by all true pairs, including missed candidate pairs. |
| F1 | Harmonic mean of precision and recall; zero if both are zero. |
| Review rate | Selected pairs sent to review divided by all selected pairs. |
| False-match examples | Up to five synthetic record ID pairs accepted automatically but absent from labels. |

On the final synthetic split, the current exact-match rule accepted 23 out of 63 true pairs;
no automatically accepted pair was wrong in this small test. Precision was 1.00, recall 0.365,
F1 0.535, blocking recall 1.00, and review rate 0.689. Forty more true pairs were selected
but held for review. No true pair was missed by blocking in this small synthetic split. These
numbers can be reproduced from the artifact; they are **not** an estimate of performance on real
people.

To keep local, queryable intermediate candidate decisions and per-split metrics as DuckDB tables:

```bash
uv run python scripts/evaluate_benchmark.py --output docs/evaluation/baseline.json \
  --database benchmarks/analysis.duckdb
```

The optional database contains only generated synthetic record IDs, selected pairs, stages,
decisions, scores, truth labels, and aggregate metrics. It is ignored by Git. Running the same
command twice replaces the two split rows rather than duplicating decisions. For example:

```sql
SELECT split, stage, decision, COUNT(*) AS pairs
FROM candidate_decisions
GROUP BY split, stage, decision;
```

The [synthetic demonstration policy](CALIBRATION.md) was selected using only tuning labels.
Its [reproducible artifact](evaluation/synthetic-policy.json) shows 30 accepted true pairs out of
63 on the held-out final split, versus 23 for the default baseline, with no observed false match
in either set. The policy remains opt-in and is not validated for real-world records. Selecting
thresholds on final outcomes would invalidate the held-out comparison.

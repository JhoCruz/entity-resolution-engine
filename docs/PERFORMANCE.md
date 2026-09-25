# Small-scale local performance measurements

Regenerate the committed [sample measurement](evaluation/performance.json) on your machine:

```bash
uv run python scripts/benchmark_performance.py --output docs/evaluation/performance.json
```

The script creates fixed-seed synthetic sources with 40, 80, 160, and 240 left records,
reconciles each size three times, and reports median full-job runtime, peak memory traced by
Python, and selected pairs relative to every possible cross-source pair. The current generator
supports at most 256 distinct left names. The artifact records the Python and operating-system
versions used for that run; **timings and allocations will differ on another machine**.

`tracemalloc` tracks Python-managed allocations during reconciliation. It does not count all
native memory used by pandas, RapidFuzz, or DuckDB; the memory values must not be interpreted
as total process RAM. Input generation is excluded from the timed interval; ingestion,
normalization, blocking, scoring, and decisions are included. The observed source sizes are
small; this script establishes how to test scaling, not that the engine handles millions of rows.

The `candidate_reduction` column is calculated as `1 - selected_pairs / possible_pairs`.
It measures avoided pair scoring, not precision or end-to-end speedup against an unbounded join.
Per-key and per-job candidate caps still reject unusually large groups. Use the separate
[`EVALUATION.md`](EVALUATION.md) artifact for match quality.

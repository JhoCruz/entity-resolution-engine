# Name candidate blocking

The `candidates` command runs the exact-identifier baseline and then searches for additional
possible pairs among configured `person_name` fields. It never turns a name-only pair into an
automatic match or a final non-match. Existing exact-ID pairs are excluded from the new count;
their original decisions and evidence remain unchanged.

## Two transparent keys

For a normalized name with at least two alphabetic tokens of at least two letters each:

1. `first_token_last_initial` groups the complete first token plus the last token's initial.
   A misspelling at the end of the last token can still leave this key unchanged.
2. `last_token_first_initial` groups the complete last token plus the first token's initial.
   A misspelling at the end of the first token can still leave this key unchanged.

Middle tokens do not contribute to either key. A pair found by both keys appears once with both
strategy names retained. The result retains source row numbers for later audit, but never stores
comparison key values or input record identifiers; the CLI prints only counts. A name with only
one token, unsupported characters at its edges, or no usable value produces no name key.
Organization names mapped as generic
`text` do not participate in this first name-based stage.

These keys are **pointers for comparison**, not evidence that two rows describe the same person.
The `reconcile` command scores selected name pairs and sends them to review; it excludes rows
already safely matched by the exact baseline. Common names can group unrelated people, and two
changed edge tokens can hide a true match. Their measured recall on one fixed synthetic
benchmark is documented in [`EVALUATION.md`](EVALUATION.md); it is not a real-world guarantee.
The `reconcile` command adds an exact-date fallback after this name stage.

## Bounded work

Every left/right pair forms part of a Cartesian product. For two sources with 10,000 records
each, that is 100,000,000 possible pairs. The command reports this possible-pair count and how
many pairs the current blocking keys select; unselected pairs are unresolved, not `no_match`.
If one name key creates more than 1,000 comparisons or all keys create more than 10,000 distinct
new pairs, generation fails with the field and limit, without printing the key or any input value.
Those limits bound pair generation; they do not establish runtime or memory benchmarks.

## Synthetic example

```bash
uv run entity-resolution-engine candidates --config examples/name-variants-job.toml
```

The fixed-seed example contains two name variations whose identifiers no longer match the left
source. Its expected summary is zero exact-ID pairs and two new name candidates, one from each
strategy. Run `scripts/generate_example_data.py` to regenerate the sources. `reconcile` scores
these two pairs, reports conflicting identifiers, and keeps both in review. Threshold calibration
remains pending; see [`REPORTS.md`](REPORTS.md) and [`DATE_BLOCKING.md`](DATE_BLOCKING.md).

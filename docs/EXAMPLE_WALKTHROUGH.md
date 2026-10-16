# Follow one pair from input to decision

These examples use only the invented records committed in `examples/data/`. They show
how the default policy handles agreement and uncertainty; they do not measure accuracy
on real records.

[generate_example_data.py](../scripts/generate_example_data.py) creates these fixtures
with the fixed seed `20260920`.

![Two synthetic record pairs: an exact match and a similar-name pair held for review](images/matching-example.svg)

## Run the examples

From the repository root, after installing the project dependencies:

```bash
uv run entity-resolution-engine reconcile --config examples/basic-job.toml --output reports/walkthrough-exact-01 --full-audit
uv run entity-resolution-engine reconcile --config examples/name-variants-job.toml --output reports/walkthrough-review-01 --full-audit
```

Each command needs a new output directory. Use a new suffix on later runs. The first
job produces four matches. The second produces two reviews and no matches. The cases
below are the first pair from each job.

## An exact match: A-001 and B-001

| Field | CSV record A-001 | Excel record B-001 | Normalized comparison |
| --- | --- | --- | --- |
| Name | `Ana Souza` | `ANA SOUZA` | `ana souza` = `ana souza` |
| Identifier | `SYN-559444-1` | `SYN5594441` | `syn5594441` = `syn5594441` |
| Birth date | `1995-06-08` | `1995-06-08` | Equal |

The identifier selects the pair. It is unique within each source, the other fields
agree, and there are no invalid values or conflicting links. The result is `match`
with reasons `exact_identifier` and `supporting_field`.

This decision comes from an exact rule. Its overall `score` is `null`; the three
individual field scores are `1.0`. It is not a fuzzy score above a threshold.

## A review: A-001 and V-001

| Field | CSV record A-001 | Variant record V-001 | Field score | Weight |
| --- | --- | --- | ---: | ---: |
| Name | `Ana Souza` | `Ana Souzax` | 0.9473684210526316 | 0.45 |
| Identifier | `SYN-559444-1` | `SYN-UNLINKED-01` | 0.0 | 0.35 |
| Birth date | `1995-06-08` | `1995-06-08` | 1.0 | 0.20 |

Both normalized names share the first token `ana` and the last initial `s`, so name
blocking selects the pair. The recorded origin is `full_name:first_token_last_initial`.
The identifiers differ, even though the names look similar and the dates agree.

The weighted similarity is approximately:

```text
(0.9473684210526316 × 0.45 + 0.0 × 0.35 + 1.0 × 0.20) / 1.0
= 0.6263157894736842
```

The result is `review`, with reasons `uncalibrated_score` and `identifier_conflict`.
The configured thresholds are `review = 0.70` and `automatic_match = 0.90`, but the
report marks them `not_calibrated_not_applied`: without an explicitly selected
calibration policy, approximate candidates stay in review regardless of their score.
Here, a score below 0.70 does not mean `no_match`.

A similarity score is not the probability that two records identify the same person.
The synthetic calibration demonstration is also not evidence of performance on real data.

## Trace the record through the code

Follow `A-001` in the second command:

1. **Read and validate.** [ingestion.py](../src/entity_resolution_engine/ingestion.py)
   loads the CSVs named in the job. [validation.py](../src/entity_resolution_engine/validation.py)
   checks the record IDs and mapped columns. Both records are on source row 2.
2. **Normalize.** [normalization.py](../src/entity_resolution_engine/normalization.py)
   preserves `Ana Souza` and `SYN-559444-1`, then creates `ana souza` and `syn5594441`
   for comparison. The variant becomes `ana souzax` and `synunlinked01`.
3. **Select candidates.** [exact_baseline.py](../src/entity_resolution_engine/exact_baseline.py)
   finds no equal identifier for this pair. [blocking.py](../src/entity_resolution_engine/blocking.py)
   selects it using the shared name anchor. Blocking avoids comparing every possible
   pair, but can miss a true pair that shares none of the available anchors.
4. **Score and decide.** [scoring.py](../src/entity_resolution_engine/scoring.py)
   computes the field evidence above and assigns `review` under the default policy.
   [reconciliation.py](../src/entity_resolution_engine/reconciliation.py) combines the
   exact, name, and date stages. Pairs that were never selected remain unresolved.
5. **Inspect the audit.** [reporting.py](../src/entity_resolution_engine/reporting.py)
   writes `reviews.jsonl` with reasons, field scores, weights, and threshold status.
   With `--full-audit`, `full/audit.jsonl` adds `left_record_id: "A-001"` and
   `right_record_id: "V-001"`. Use their `left_ref` and `right_ref` to find the original
   and normalized values in `full/normalized_left.jsonl` and
   `full/normalized_right.jsonl`. These opaque references change between runs.

`summary.json` contains job counts. `matches.jsonl`, `reviews.jsonl`, and
`non_matches.jsonl` contain explicit decisions; `conflicts.jsonl` is a subset of reviews.
Without `--full-audit`, reports omit original values and record IDs. The full audit
in these commands is useful for following the invented example values locally.

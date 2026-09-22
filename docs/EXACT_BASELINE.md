# Exact-identifier baseline

The first matching stage takes two validated, normalized sources. It finds candidate pairs only
when at least one configured `identifier` field has the same nonempty comparison key on both
sides. An invalid field or an empty key cannot create a candidate. Multiple matching identifier
fields still produce a single pair with every originating field recorded in `matched_on`.

## Decisions

A candidate is an automatic `match` only if all these conditions hold:

1. Its left and right rows each have exactly one candidate partner overall.
2. No originating identifier key is duplicated within either source.
3. At least one *non-identifier* mapped field also agrees exactly.
4. No field with two usable comparison keys conflicts, and neither side has an invalid mapped
   value for that candidate.

Otherwise it becomes `review`, with stable reasons such as `identifier_collision`,
`one_to_many`, `many_to_one`, `field_conflict`, `invalid_field`, or `no_supporting_field`.
Each `FieldEvidence` records its name and semantic type, outcome, exact component score (`1.0`
for agreement, `0.0` for conflict, null for missing/invalid), and applicable normalization issues.
No source field values are included in field evidence. Internal pair objects retain source row
numbers and original record IDs for future audited reports; their representation hides those IDs.

This is a deterministic rule, so it does not claim a probabilistic confidence score. The
configured `review` and `automatic_match` thresholds are reserved for the later scored stage.
An exact identifier with a conflicting name or date remains reviewable: a shared key alone is
insufficient to decide which input contains the mistake.

## Rows without candidates

Rows without an exact-identifier candidate are recorded separately. They are **not** final
`no_match` decisions: later blocking and fuzzy comparisons may still find the same entity.
Jobs without an identifier mapping simply leave every row available for those later stages.

Repeated identifiers may generate many pair combinations. The baseline fails safely when one
shared key would create more than 1,000 pairs or when all keys together create more than 10,000
distinct pairs. Errors state the field and limit without printing identifier values.

## Run the synthetic example

```bash
uv run entity-resolution-engine baseline --config examples/basic-job.toml
```

The CLI prints only counts and review reason totals. It never prints row IDs or source field
values. The example data is synthetic and can be regenerated with the fixed-seed generator at
`scripts/generate_example_data.py`. The `inspect` command still stops after input validation.

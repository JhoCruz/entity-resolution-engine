# Local reconciliation reports

Run both sources through the full pipeline with:

```bash
uv run entity-resolution-engine reconcile --config examples/name-variants-job.toml \
  --output reports/variants
```

The output directory must not already exist. Missing parent directories are created. The command
prints counts and the output location; it never prints record values. `--full-audit` adds a separate
`full/` directory with source values. Reports use JSON Lines (`.jsonl`), one decision per line.

## Reduced view (default)

| File | Contents |
| --- | --- |
| `summary.json` | Counts of rows, possible and selected pairs, name and date candidates, decisions, conflicts, and rows without candidates. |
| `matches.jsonl` | Automatically accepted exact-identifier pairs and their field evidence. |
| `reviews.jsonl` | Ambiguous exact pairs and all currently scored name or date pairs. |
| `non_matches.jsonl` | Explicitly rejected candidate pairs; currently empty pending calibration. |
| `conflicts.jsonl` | A subset of reviews with conflicting fields, for triage. |

Each pair includes `left_ref` and `right_ref`, random opaque references unique to one run,
decision, stage, safe reasons, and evidence containing field names, field types, outcomes, and
scores. Name and date candidates also include blocking strategies, configured weights, a weighted
similarity, and the configured thresholds with status `not_calibrated_not_applied`.

Only available, valid field values contribute to the weighted mean. Person names and generic
text use normalized character similarity; identifiers, dates, phones, and e-mails contribute
only exact agreement (1) or conflict (0). Missing and invalid values have no score, and their
absence remains visible in evidence. A high similarity can still describe two different people.
All name- and date-based pairs therefore receive `review` until thresholds are calibrated on
labeled data. Date-only candidates are marked `date_only_candidate`, because a matching birthday
alone cannot establish identity.
The exact-identifier stage uses its own documented conservative evidence rules, not a fuzzy score.

The references change on every run and cannot be joined to row numbers without the full view.
They are pseudonyms, not a claim of legal anonymity. Field names or rare combinations of scores
can still disclose context in a particular setting. Keep reports under appropriate access control.

Pairs not selected by blocking are **unresolved**, not `no_match`. A row with no selected pair is
counted in the summary, not assigned an invented outcome. `conflicts.jsonl` intentionally repeats
some `reviews.jsonl` rows; do not add the file counts as if they were disjoint.

## Full local audit (explicit opt-in)

```bash
uv run entity-resolution-engine reconcile --config examples/name-variants-job.toml \
  --output reports/variants-audit --full-audit
```

The `full/normalized_left.jsonl` and `full/normalized_right.jsonl` files contain all mapped
fields side by side with original and normalized values, transformation steps, normalization
issues, original source row numbers, and record identifiers. `full/audit.jsonl` adds those row
numbers and identifiers to each pair decision. Use the shared `row_ref` to relate a pair in the
reduced view to the corresponding normalized rows. Only the full view contains source values.
Generated files use owner-only permissions on systems that support them. Do not commit or share
the full view if it contains real personal data; store it in a directory with suitable access
controls. This tool does not determine whether a real-world workflow complies with privacy law.

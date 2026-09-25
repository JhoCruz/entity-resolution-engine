# Date candidate fallback

The `reconcile` command looks for pairs with the same valid, normalized `date` field after the
exact-identifier and person-name candidate stages. It excludes pairs already selected, and rows
already accepted by the exact stage. An invalid, ambiguous, or missing date produces no key.

Sharing a date is **not proof of identity**. All date-only pairs receive `review` even when their
names look similar and the weighted similarity is high. The report marks them with the
`date_only_candidate` reason and keeps conflicts visible. An unrelated person born on the same
day can be suggested for review; explicit decisions on unselected pairs are never invented.

At most 1,000 comparisons may arise from one date key, and at most 10,000 new date pairs may
arise overall. Jobs exceeding either limit fail with the field name and limit without revealing
the date itself. These limits bound candidate generation, not total source size.

The fixed-seed benchmark initially selected 52 of 63 true pairs with exact identifiers or the
two name anchors in its final split. Adding the date key recovered the remaining 11, raising
blocking recall from 0.825 to 1.00 on **that synthetic split only**. It also introduced more
unrelated suggestions for human review. See [`EVALUATION.md`](EVALUATION.md) for the current
artifact and limitations.

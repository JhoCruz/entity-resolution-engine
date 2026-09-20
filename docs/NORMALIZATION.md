# Normalization contract

Normalization creates comparison values from validated source fields. It never changes the loaded
data frame. Each logical field produces three adjacent columns:

| Column | Purpose |
| --- | --- |
| `<field>_original` | Exact source value retained for audit and reporting. |
| `<field>_normalized` | Canonical string reserved for comparison. |
| `<field>_transformations` | Ordered names of transformations that changed the value. |

Every normalized table also retains `source_record_id` and `source_row` so a comparison value can
always be traced back to its source record.

## Baseline transformation order

The baseline applies only the following standard-library transformations, in this exact order:

| Step | Behavior | Information loss |
| --- | --- | --- |
| `coerce_to_text` | Convert a non-string scalar with `str`. | Type information is absent from the comparison string but remains in the original column. |
| `unicode_nfkc` | Apply Unicode NFKC compatibility normalization. | Width variants and compatibility characters such as ligatures become canonical forms. |
| `case_fold` | Apply Unicode-aware `casefold`. | Letter casing is removed; some characters expand, such as `ß` to `ss`. |
| `punctuation_to_space` | Replace characters in Unicode punctuation categories with spaces. | Punctuation distinctions are removed. Symbols such as `+` are retained. |
| `whitespace_collapse` | Trim and collapse every whitespace run to one ASCII space. | Original spacing and whitespace types are removed. |

Only steps that actually change a value are recorded. Null-like values remain null and receive no
transformations. Composite cell values such as lists or dictionaries are rejected instead of being
silently stringified. Running the baseline again on its own output produces the same comparison
value.

## Deliberate limits

The baseline preserves diacritics and does not interpret identifiers, dates, phone numbers, or
e-mail addresses. Their semantic normalizers belong to later Milestone 2 increments. Matching and
scoring must not infer meaning from this baseline alone.

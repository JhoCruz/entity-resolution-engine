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

## Semantic extensions

Semantic normalizers run after the baseline. They reuse its scalar validation, null handling, and
audit trail, then append a semantic transformation only when it changes the comparison value.

| Semantic type | Added step | Behavior | Information loss |
| --- | --- | --- | --- |
| `person_name` | `diacritics_removed` | Decompose Unicode characters, remove combining marks, and recompose the result. | Accent and other combining-mark distinctions are removed. |
| `identifier` | `non_alphanumeric_removed` | Retain only Unicode letters and digits. | Separators, whitespace, punctuation, and symbols are removed. |

Person-name normalization keeps particles and token order. It does not expand nicknames, reorder
names, apply phonetic rules, or transliterate distinct letters such as `ø` into `o`. Those choices
can merge different people and belong in later, measured comparison logic rather than silent
normalization.

Identifier normalization is deliberately generic. It preserves leading zeros and Unicode letters
and digits, but does not guess an identifier type, validate a checksum, or infer a country. A value
containing only formatting becomes an empty string, not a missing value, so later validation or
matching logic can distinguish the two states.

## Deliberate limits

The baseline itself preserves diacritics. Only `person_name` and `identifier` currently add
field-specific behavior. Dates, phone numbers, and e-mail addresses still use the baseline and will
receive dedicated, conservative rules in later Milestone 2 increments. Matching and scoring must
not infer meaning from the baseline alone.

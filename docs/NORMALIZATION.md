# Normalization contract

Normalization creates comparison values from validated source fields. It never changes the loaded
data frame. Each logical field produces four adjacent columns:

| Column | Purpose |
| --- | --- |
| `<field>_original` | Exact source value retained for audit and reporting. |
| `<field>_normalized` | Canonical string reserved for comparison. |
| `<field>_transformations` | Ordered names of transformations that changed the value. |
| `<field>_issue` | Reason a present value has no safe comparison key, or null if there is no issue. |

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

Person names and identifiers extend the baseline. The structured formats below preserve
syntax-significant punctuation and casing, so they validate the original scalar before creating a
comparison key. All normalizers retain the same missing-value behavior and audit metadata.

| Semantic type | Added step | Behavior | Information loss |
| --- | --- | --- | --- |
| `person_name` | `diacritics_removed` | Decompose Unicode characters, remove combining marks, and recompose the result. | Accent and other combining-mark distinctions are removed. |
| `identifier` | `non_alphanumeric_removed` | Retain only Unicode letters and digits. | Separators, whitespace, punctuation, and symbols are removed. |
| `phone` | `unicode_nfkc`, `outer_whitespace_trim`, `phone_formatting_removed`, `phone_extension_canonicalized` | Preserve an explicit `+`, the digit sequence, and an optional `x` extension. | Width, separator, and extension-label distinctions are removed. |
| `date` | `unicode_nfkc`, `outer_whitespace_trim`, `coerce_to_text`, `datetime_to_date` | Accept validated `YYYY-MM-DD` strings and date cells; midnight-only, naive datetime cells become dates. | Datetime type and the zero time are removed from the key; the original remains available. |
| `email` | `outer_whitespace_trim`, `email_domain_lowercase` | Preserve an ASCII dot-atom local part exactly and lowercase its ASCII domain. | Outer whitespace and domain casing are removed. |

Person-name normalization keeps particles and token order. It does not expand nicknames, reorder
names, apply phonetic rules, or transliterate distinct letters such as `ø` into `o`. Those choices
can merge different people and belong in later, measured comparison logic rather than silent
normalization.

Identifier normalization is deliberately generic. It preserves leading zeros and Unicode letters
and digits, but does not guess an identifier type, validate a checksum, or infer a country. A value
containing only formatting becomes an empty string, not a missing value, so later validation or
matching logic can distinguish the two states.

### Phone, date, and e-mail rules

Phones accept ASCII digits, spaces, dots, hyphens, and balanced parentheses, optionally starting
with `+`. A suffix such as `x07` or `ext. 07` becomes `x07`. The dialling number must contain 3 to
15 digits. A `+` remains part of the key: `+5548999991234` and `5548999991234` do not compare as
equal automatically. National numbers keep their leading zeros. Country codes, trunk prefixes,
extensions, and short codes are never guessed. The 15-digit cap follows the international maximum
in [ITU-T E.164](https://www.itu.int/rec/T-REC-E.164-202602-I); this syntax check does not prove a
number is assigned or reachable.

Dates accept exact zero-padded `YYYY-MM-DD` strings and actual `date` cells, including Excel date
cells represented as naive midnight `datetime` objects. The calendar is validated, including leap
years. `03/04/2024` is flagged as `ambiguous_date`; other local formats, non-midnight or timezone
aware datetimes, and numeric spreadsheet serials are flagged as `unsupported_date`. To handle
`DD/MM/YYYY` later, the source format must be configured explicitly instead of guessed.

E-mail addresses accept the common unquoted ASCII dot-atom local part and ASCII domain labels.
The local part is kept exactly, including case, dots, and plus tags; only the domain is lowercased.
For example, `First+Tag@EXAMPLE.COM` becomes `First+Tag@example.com`. [RFC 5321](https://www.rfc-editor.org/rfc/rfc5321)
requires local-part case to be preserved. Provider-specific dot or plus aliasing is never assumed.
Quoted local parts, internationalized addresses, and domain literals are flagged as unsupported,
even if some are valid in a broader e-mail standard.

### Invalid and ambiguous values

For an unsupported or ambiguous present value, `<field>_normalized` is null and `<field>_issue`
holds one of `unsupported_phone`, `ambiguous_date`, `invalid_date`, `unsupported_date`, or
`unsupported_email`. A missing value has a null key *and* a null issue. The issue contains no input
value or record identifier; the original column is retained for authorized review. Already applied
preparation steps such as Unicode normalization or trimming are still recorded. A downstream
matcher must never treat a null key as positive evidence.

## Deliberate limits

The baseline preserves diacritics. The structured-format rules deliberately accept a limited,
documented syntax. Other conventions can be added only with explicit source configuration and
tests demonstrating that distinct values will not collapse silently. No candidate generation or
matching uses these keys yet; `inspect` currently ends after source validation.

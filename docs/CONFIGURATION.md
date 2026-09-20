# Job configuration

A TOML file describes the two sources in one resolution job. The configuration is validated
before file ingestion begins, so spelling mistakes and ambiguous mappings fail with a precise
location instead of producing a misleading match result later.

See [`examples/basic-job.toml`](../examples/basic-job.toml) for a complete synthetic example.

Validate it from the command line:

```bash
uv run entity-resolution-engine check-config examples/basic-job.toml
```

Load and validate both example sources without printing their record values:

```bash
uv run entity-resolution-engine inspect --config examples/basic-job.toml
```

## Sources

Each job has a `left` and `right` source.

| Key | Meaning |
| --- | --- |
| `path` | CSV or XLSX path, resolved relative to the configuration file. |
| `file_type` | Explicit `csv` or `xlsx` format. |
| `record_id` | Column that uniquely identifies a row inside that source. |
| `worksheet` | Optional worksheet name, accepted only for XLSX sources. |
| `delimiter` | Optional one-character CSV separator; defaults to `,`. |
| `encoding` | Optional CSV text encoding; defaults to `utf-8`. |

The configured extension must agree with `file_type`. File existence and source columns are
checked by the ingestion layer. CSV options are rejected on XLSX sources.

## Ingestion behavior

CSV and XLSX files are loaded into pandas data frames without trimming, normalizing, or replacing
cell values. Each loaded source also retains logical row numbers, starting at row 2 because row 1
contains the header. The selected Excel worksheet and original source configuration remain attached
to the loaded result for later audit reports.

Missing files, directories, empty sources, decoding failures, malformed CSV files, corrupt
workbooks, and missing worksheets produce errors that include the source path and relevant context.

## Source validation behavior

After loading, each source is checked against its configured record identifier and field mappings.
Validation blocks downstream processing when:

- the source has no data rows;
- a required column is missing or a column name is duplicated;
- a record identifier is null, blank, or duplicated.

Independent problems from both sources are collected into one structured result when possible.
Messages include the source path, affected columns, counts, and bounded samples of logical row
numbers. They deliberately omit record identifier values. Unexpected columns are reported as
non-blocking warnings and remain unchanged in the loaded data.

## Field mappings

Every `[[field_mappings]]` entry gives one logical field a stable name and identifies its source
columns.

| Key | Meaning |
| --- | --- |
| `name` | Stable lowercase identifier used in reports and rules. |
| `left_column` | Exact column name in the left source. |
| `right_column` | Exact column name in the right source. |
| `semantic_type` | `text`, `person_name`, `identifier`, `date`, `email`, or `phone`. |
| `weight` | Positive relative importance reserved for the scoring milestone. |

Logical names and source columns must be unique within their respective sides. A source's
`record_id` cannot also be a matching field because it identifies rows for audit and reporting.

## Thresholds

Thresholds remain separate from field definitions:

```toml
[thresholds]
automatic_match = 0.90
review = 0.70
```

Scores at or above `automatic_match` become automatic matches. Scores at or above `review`, but
below `automatic_match`, require review. Lower scores become non-matches. The configuration
rejects thresholds outside `0..1` and requires `review < automatic_match`.

## Loading from Python

```python
from entity_resolution_engine.config import load_config

config = load_config("examples/basic-job.toml")
print(config.field_mappings)
```

Loading the configuration validates the complete contract and always resolves relative paths from
the TOML file's directory, regardless of the shell's current working directory. Source files are
loaded separately by `entity_resolution_engine.ingestion.load_source` or `load_sources`, then
checked by `entity_resolution_engine.validation.validate_source` or `validate_sources`.

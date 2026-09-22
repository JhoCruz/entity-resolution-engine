# Roadmap

The milestones intentionally follow the data pipeline. A milestone is complete only when its
acceptance criteria pass locally and in CI.

## Milestone 0: Repository foundation

- [x] Installable Python package with `src/` layout.
- [x] Working CLI and environment check.
- [x] Typed confidence decision policy with a review region.
- [x] Automated tests, coverage gate, linting, formatting, and static type checking.
- [x] CI workflow, Dockerfile, contribution templates, and privacy rules.
- [x] Architecture decision record for the initial technical choices.

## Milestone 1: Data contracts and ingestion

- [x] Define source and field mapping configuration.
- [x] Read CSV and XLSX without mutating original values.
- [x] Validate required columns, record identifiers, empty inputs, and duplicate identifiers.
- [x] Produce actionable errors containing file and column context.
- [x] Cover successful and failing paths with synthetic fixtures.
- [x] Inspect both configured sources through one safe CLI command.

## Milestone 2: Normalization

- [x] Normalize Unicode, whitespace, punctuation, and casing safely.
- [x] Add field-specific normalization:
  - [x] Person names with diacritic-insensitive keys that preserve particles and token order.
  - [x] Generic identifiers that remove formatting without losing leading zeros.
  - [x] Phone numbers with explicit country-code and extension rules.
  - [x] Dates with explicit formats and no ambiguous day/month guessing.
  - [x] E-mail addresses with standards-aware local-part and domain handling.
- [x] Preserve original and normalized values side by side.
- [x] Document every lossy transformation and test its edge cases.
- [x] Flag invalid or unsupported structured values separately from missing values.

## Milestone 3: Deterministic baseline

- [x] Match unique exact identifiers only with independent supporting evidence.
- [x] Define agreement and conflict rules across multiple fields.
- [x] Emit exact component evidence and review reasons without source values in CLI output.
- [x] Detect ambiguous one-to-many and many-to-one matches.
- [x] Keep rows with no exact-ID candidate available for later matching stages.

## Milestone 4: Candidate blocking and fuzzy scoring

- [ ] Demonstrate why an unrestricted Cartesian comparison is unacceptable.
- [ ] Implement at least two transparent blocking strategies.
- [ ] Measure blocking recall against labeled ground truth.
- [ ] Combine field similarities with configurable weights.
- [ ] Calibrate `match`, `review`, and `no_match` thresholds on validation data only.

## Milestone 5: Synthetic benchmark and evaluation

- [ ] Generate `pt_BR` entities with Faker and a fixed seed.
- [ ] Apply controlled missingness, typos, transpositions, formatting changes, and conflicts.
- [ ] Retain hidden entity identifiers as ground truth.
- [ ] Report precision, recall, F1, review rate, and false-match examples.
- [ ] Separate training/tuning data from the final benchmark.

## Milestone 6: Performance and stable CLI

- [ ] Benchmark runtime, memory, and candidate reduction at increasing dataset sizes.
- [ ] Store intermediate analytical tables and evaluation results in DuckDB.
- [ ] Reconcile two files through one documented command.
- [ ] Export matches, reviews, non-matches, conflicts, and a summary report.
- [ ] Provide two explicit local report views: a reduced view with aggregate counts and per-run
  opaque references for row-level decisions, without names, identifiers, phones, e-mails, source
  values, normalized personal values, or stable hashes; and an opt-in full audit view with
  original and normalized values, provenance, evidence, and reasons.
- [ ] Test that the reduced view does not disclose values from synthetic input fixtures; keep the
  full view out of logs and repository artifacts. Do not label the reduced view legally anonymous
  without assessing whether records can be re-identified in its intended context.
- [ ] Build and test the container image.
- [ ] Tag `v1.0.0` only after every documented command is reproducible.

## Deferred work

- interactive dashboard;
- probabilistic or learned linkage models;
- API and hosted deployment;
- distributed execution;
- embeddings or LLM-assisted review.

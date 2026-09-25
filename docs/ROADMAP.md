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

- [x] Demonstrate why an unrestricted Cartesian comparison is unacceptable.
- [x] Implement two bounded, transparent person-name blocking strategies with no match decisions.
- [x] Recover missed name pairs through a bounded exact-date key, always requiring review.
- [x] Measure blocking recall against labeled ground truth.
- [x] Combine field similarities with configurable weights; abstain on name pairs pending calibration.
- [x] Tune demonstration `match`, `review`, and `no_match` thresholds on labeled synthetic
  tuning data only, then assess the chosen policy on held-out synthetic data. Default remains
  review-only; real-world calibration requires separately permitted labeled data.

## Milestone 5: Synthetic benchmark and evaluation

- [x] Generate Brazilian-style invented entities with a curated pool and fixed seed.
- [x] Apply controlled missingness, typos, transpositions, formatting changes, and conflicts.
- [x] Retain hidden entity identifiers as separate ground truth.
- [x] Report precision, recall, F1, review rate, and false-match examples.
- [x] Separate tuning data from the final benchmark.

## Milestone 6: Performance and stable CLI

- [x] Benchmark runtime, traced Python allocations, and candidate reduction at increasing
  synthetic dataset sizes, documenting that traced allocations exclude native memory.
- [x] Store synthetic intermediate candidate decisions and per-split evaluation results in DuckDB.
- [x] Reconcile two files through one documented command.
- [x] Export matches, reviews, non-matches, conflicts, and a summary report (no approximate
  non-match decision until calibrated).
- [x] Provide two explicit local report views: a reduced view with aggregate counts and per-run
  opaque references for row-level decisions, without names, identifiers, phones, e-mails, source
  values, normalized personal values, or stable hashes; and an opt-in full audit view with
  original and normalized values, provenance, evidence, and reasons.
- [x] Test that the reduced view does not disclose values from synthetic input fixtures; keep the
  full view out of logs and repository artifacts. Do not label the reduced view legally anonymous
  without assessing whether records can be re-identified in its intended context.
- [x] Build and test the container image in CI (including its entry point).
- [ ] Tag `v1.0.0` only after every documented command is reproducible.

## Deferred work

- interactive dashboard;
- probabilistic or learned linkage models;
- API and hosted deployment;
- distributed execution;
- embeddings or LLM-assisted review.

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

- [ ] Define source and field mapping configuration.
- [ ] Read CSV and XLSX without mutating original values.
- [ ] Validate required columns, record identifiers, empty inputs, and duplicate identifiers.
- [ ] Produce actionable errors containing file and column context.
- [ ] Cover successful and failing paths with synthetic fixtures.

## Milestone 2: Normalization

- [ ] Normalize Unicode, whitespace, punctuation, and casing safely.
- [ ] Add field-specific normalization for names, identifiers, phone numbers, dates, and e-mails.
- [ ] Preserve original and normalized values side by side.
- [ ] Document every lossy transformation and test its edge cases.

## Milestone 3: Deterministic baseline

- [ ] Match trustworthy exact identifiers.
- [ ] Define agreement and conflict rules across multiple fields.
- [ ] Emit component evidence and rejection reasons.
- [ ] Detect ambiguous one-to-many and many-to-one matches.

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
- [ ] Build and test the container image.
- [ ] Tag `v1.0.0` only after every documented command is reproducible.

## Deferred work

- interactive dashboard;
- probabilistic or learned linkage models;
- API and hosted deployment;
- distributed execution;
- embeddings or LLM-assisted review.

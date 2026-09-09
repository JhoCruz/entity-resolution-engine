# ADR 0001: Start with an auditable local pipeline

- **Status:** Accepted
- **Date:** 2026-09-09

## Context

The project must demonstrate data engineering, algorithmic reasoning, software quality, and honest
evaluation within a portfolio-sized scope. Entity resolution is vulnerable to false confidence:
an opaque similarity score can be operationally worse than an obvious non-match.

## Decision

- Build an installable Python 3.12 package with a local CLI as the first interface.
- Use pandas/openpyxl for familiar tabular ingestion and DuckDB for inspectable SQL analytics.
- Establish deterministic rules before fuzzy matching.
- Use RapidFuzz for transparent string similarities when approximate matching is introduced.
- Represent uncertainty explicitly through `match`, `review`, and `no_match` decisions.
- Use only seeded synthetic data with known ground truth.
- Enforce tests, linting, formatting, type checking, and coverage in CI.

## Consequences

The first release remains easy to run and explain, and every reported result can be reproduced.
The project postpones a web interface, cloud deployment, learned models, and distributed processing.
Those capabilities may be justified later by measured limitations rather than added speculatively.

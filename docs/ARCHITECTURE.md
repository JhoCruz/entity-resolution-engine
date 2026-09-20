# Architecture

## Goal

Resolve records that refer to the same entity while making uncertainty, evidence, and failure
modes visible. The first stable release targets local CSV/XLSX workflows through a CLI.

## Processing stages

1. **Ingestion** reads tabular sources without altering the originals.
2. **Validation** checks schemas, types, required fields, and duplicate source identifiers.
3. **Normalization** produces comparable representations while retaining original values.
4. **Candidate generation** reduces the Cartesian product through deterministic blocking keys.
5. **Scoring** combines field-level exact and approximate similarities.
6. **Decision policy** maps scores to `match`, `review`, or `no_match`.
7. **Reporting** records decisions, component scores, reasons, and provenance.
8. **Evaluation** compares decisions with synthetic ground truth and measures quality and cost.

## Planned package boundaries

```text
entity_resolution_engine/
├── cli.py              # User-facing command orchestration
├── config.py           # Typed source, field mapping, and threshold contracts
├── decision.py         # Thresholds and abstention policy
├── ingestion.py        # CSV/XLSX loading and row provenance
├── validation.py       # Source schemas and record identifiers
├── normalization.py    # Field-specific canonicalization
├── blocking.py         # Candidate generation
├── scoring.py          # Pair-level evidence and confidence
├── reporting.py        # Auditable output tables
└── evaluation.py       # Accuracy and performance measurement
```

Modules are added only when their milestone begins. Empty architecture is documentation, not code.

## Data flow guarantees

- Original values remain available in reports.
- Loaded records retain their source path, worksheet, and logical row number.
- Missing mapped columns and invalid record identifiers block downstream processing.
- Independent validation failures are returned together without exposing identifier values.
- Normalized values never overwrite source data.
- Every changed comparison value retains ordered normalization-step metadata.
- A match stores the exact rules and component scores that produced it.
- Thresholds are explicit configuration, never hidden constants.
- Ambiguous cases remain reviewable rather than silently forced into a binary decision.

## Initial non-goals

- graphical or web interface;
- authentication and multi-user workflows;
- distributed processing or Kubernetes;
- cloud-specific infrastructure;
- LLM or embedding-based matching;
- domain-specific employer logic.

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
├── exact_baseline.py   # Safe exact-identifier candidates and decisions
├── blocking.py         # Candidate generation
├── date_blocking.py    # Bounded exact-date candidate fallback
├── scoring.py          # Pair-level evidence and confidence
├── reporting.py        # Auditable output tables
└── evaluation.py       # Accuracy and performance measurement
```

Modules are added only when their milestone begins. Empty architecture is documentation, not code.

## Data flow guarantees

- Original values remain available for an explicitly requested local full audit report; the
  default reduced report must not include original or normalized personal values.
- Loaded records retain their source path, worksheet, and logical row number.
- Missing mapped columns and invalid record identifiers block downstream processing.
- Independent validation failures are returned together without exposing identifier values.
- Normalized values never overwrite source data.
- Every changed comparison value retains ordered normalization-step metadata.
- Unsupported or ambiguous phone, date, and e-mail values retain a reason and cannot become
  automatic comparison keys.
- A match stores the exact rules and component scores that produced it.
- Thresholds are explicit configuration, never hidden constants.
- Ambiguous cases remain reviewable rather than silently forced into a binary decision.
- Rows not found by exact identifiers remain eligible for later candidate strategies.
- Name blocking adds candidates through two bounded keys. Date blocking adds candidates through
  a bounded valid-date key after removing existing pairs. Exact decisions remain unchanged. The
  full CLI scores additional pairs and requires review by default; the synthetic demonstration
  policy can be explicitly selected with its field contract and one-to-one safeguards.

## Report privacy boundary

The CLI prints aggregate counts and output locations. The default reduced view includes counts
and row-level decisions identified only by opaque references created for that run, plus field-level
evidence without values. The opt-in full audit retains original and normalized values needed to
investigate a decision, and is written locally without printing personal values in CLI output.
An opaque reference is a pseudonym for review, not a guarantee of legal anonymization: linked
records or other context may still permit re-identification. Normalizing a name, phone, or
personal identifier does not make it anonymous. Both views use synthetic examples in this
repository; operators are responsible for access control and lawful use of any real inputs.

## Initial non-goals

- graphical or web interface;
- authentication and multi-user workflows;
- distributed processing or Kubernetes;
- cloud-specific infrastructure;
- LLM or embedding-based matching;
- domain-specific employer logic.

# Data policy

Only reproducible synthetic data belongs in this repository.

The benchmark generator planned for Milestone 5 will use Faker with the `pt_BR` locale, a fixed
random seed, and controlled corruptions. It will emit both the altered records and the hidden
ground-truth entity identifiers needed for evaluation.

Never add:

- employer or institutional data;
- real names, identifiers, addresses, phone numbers, or e-mail addresses;
- internal schemas, screenshots, exports, or procedure descriptions;
- raw files received from another person without an explicit redistribution license.

Large generated datasets and local outputs are ignored by Git. Small deterministic fixtures used
by automated tests may be committed under `tests/fixtures/` when they contain no real PII.

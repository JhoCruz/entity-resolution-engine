# First demo: two small, synthetic datasets

This walkthrough takes about five minutes. It uses only the invented records in `examples/`.
The tool compares rows from two sources and reports which pairs it can accept, which need
review, and which pairs it never selected for comparison.

## Run it

Install Python 3.12 or newer and [`uv`](https://docs.astral.sh/uv/), then run from a terminal:

```bash
git clone https://github.com/JhoCruz/entity-resolution-engine.git
cd entity-resolution-engine
uv sync --locked
uv run entity-resolution-engine doctor
uv run entity-resolution-engine reconcile --config examples/basic-job.toml --output reports/first-demo
uv run entity-resolution-engine reconcile --config examples/name-variants-job.toml --output reports/variants-demo
```

Each `--output` path must be new. To repeat a command, choose a different path, such as
`reports/first-demo-2`. The input examples are included in the repository; no spreadsheet
editing or credentials are required. The commands above also work in Windows PowerShell when
`uv` is on your PATH.

## What to expect

| Run | Input rows | Selected pairs | Automatic matches | Reviews |
| --- | --- | --- | --- | --- |
| `basic-job.toml` | 4 left, 4 right | 4 of 16 possible | 4 | 0 |
| `name-variants-job.toml` | 4 left, 2 right | 2 of 8 possible | 0 | 2 |

The first example has distinct matching identifiers with independent supporting fields.
The second has altered names and matching dates, but its invented identifiers conflict with
the left source. Both selected pairs are suggestions for **review**, not accepted identities.
The other 12 and 6 possible pairs, respectively, were not selected; the tool does not claim
that those pairs are different people.

Open `reports/first-demo/summary.json` and `reports/variants-demo/summary.json` in a text
editor to see the counts. Each output directory also contains `matches.jsonl`,
`reviews.jsonl`, `non_matches.jsonl`, and `conflicts.jsonl`. A `.jsonl` file contains one JSON
decision per line. In the second run, both reviews are also copied to `conflicts.jsonl` for
triage, so do not add those counts together.

The default reports show random per-run row references, field scores, and reasons, but no
source names, identifiers, or original row numbers. If you explicitly need original and
normalized values for this **synthetic** example, run a third command with a new path:

```bash
uv run entity-resolution-engine reconcile --config examples/name-variants-job.toml --output reports/variants-full-demo --full-audit
```

Look in `reports/variants-full-demo/full/` for the original and normalized rows and the
pair audit. A real dataset could put personal information in this directory. Do not commit
or share it. The default reduced view uses pseudonymous references; it is not a legal
anonymity guarantee.

## Explain the result

> The engine reads two CSV or Excel sources using an explicit field mapping. It validates
> and normalizes the inputs, narrows down candidate pairs, and keeps the evidence for each
> decision. Exact identifiers need other supporting evidence to be accepted. Similar names
> can surface a possible pair, but uncertain or conflicting evidence goes to review.

In a technical discussion, be ready to open `summary.json` and answer these questions:

- **Why not compare every row with every other row?** Candidate selection bounds the work;
  the summary shows both possible and selected pair counts. It may miss pairs, so unselected
  pairs remain unresolved.
- **Why are the name variants not automatic matches?** Similar spelling and a shared date
  are insufficient here, especially with conflicting identifiers. The default policy sends
  approximate pairs to review.
- **What is the privacy boundary?** The ordinary report omits source values; the explicit
  full audit contains them and stays local. Neither option establishes legal anonymization.

The measured accuracy and performance elsewhere in this repository use generated records.
They do not demonstrate accuracy on real people or fitness for a production identity system.

"""Generate reproducible Brazilian-style synthetic records with hidden pair labels.

Run: uv run python scripts/generate_benchmark.py --output-directory benchmarks/tuning
"""

from __future__ import annotations

import argparse
import csv
import random
from datetime import date
from pathlib import Path

GIVEN_NAMES = (
    "Ana",
    "Bruno",
    "Camila",
    "Diego",
    "Elisa",
    "Fabio",
    "Gabriela",
    "Hugo",
    "Iris",
    "Joao",
    "Karina",
    "Lucas",
    "Marina",
    "Nilo",
    "Olivia",
    "Paulo",
)
FAMILY_NAMES = (
    "Avelar",
    "Bastos",
    "Cardoso",
    "Duarte",
    "Esteves",
    "Farias",
    "Gomes",
    "Lopes",
    "Martins",
    "Nunes",
    "Pereira",
    "Queiroz",
    "Rocha",
    "Souza",
    "Tavares",
    "Viana",
)
LEFT_COLUMNS = ("row_id", "name", "identity", "birth_date")
RIGHT_COLUMNS = ("row_id", "name", "identity", "birth_date")
LABEL_COLUMNS = ("entity_key", "left_record_id", "right_record_id")


def _write_csv(path: Path, columns: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _change_first_letter(value: str, replacement: str) -> str:
    return replacement + value[1:]


def _transpose_middle(value: str) -> str:
    """Exchange two interior letters while keeping the blocking initial."""
    return value[0] + value[2] + value[1] + value[3:]


def generate_benchmark(directory: Path, *, seed: int = 20260925, size: int = 80) -> None:
    """Write job sources and separate, never-ingested ground truth using only invented IDs."""
    if not 8 <= size <= len(GIVEN_NAMES) * len(FAMILY_NAMES):
        raise ValueError("Benchmark size must be between 8 and 256.")
    directory.mkdir(parents=True, exist_ok=True)
    generator = random.Random(seed)
    names = [f"{first} {last}" for first in GIVEN_NAMES for last in FAMILY_NAMES]
    generator.shuffle(names)
    left_rows: list[dict[str, str]] = []
    right_rows: list[dict[str, str]] = []
    labels: list[dict[str, str]] = []

    for index in range(size):
        name = names[index]
        first, last = name.split()
        birth = date(
            generator.randrange(1975, 2003), generator.randrange(1, 13), generator.randrange(1, 29)
        ).isoformat()
        identity = f"SYN-{index:06d}"
        left_id, right_id = f"L-{index:04d}", f"R-{index:04d}"
        left_rows.append(
            {"row_id": left_id, "name": name, "identity": identity, "birth_date": birth}
        )

        variant = generator.choices(range(8), weights=(20, 10, 12, 15, 10, 10, 8, 15), k=1)[0]
        if variant == 7:  # Some left entities genuinely have no record in the other source.
            continue
        right_name, right_identity, right_birth = name, identity, birth
        if variant == 1:
            right_identity = identity.replace("-", "")
        elif variant == 2:
            right_name = f"{first} {_transpose_middle(last)}"
        elif variant == 3:
            right_name = f"{first} {last}x"
            right_identity = ""
        elif variant == 4:
            right_name = f"{first}o {last}"
            right_identity = f"SYN-CHANGED-{index:06d}"
        elif variant == 5:
            right_birth = date(1970, 1, 1).isoformat()
        elif variant == 6:
            # Both edge tokens change: neither name blocking key can recover this pair.
            right_name = f"{_change_first_letter(first, 'Z')} {_change_first_letter(last, 'X')}"
            right_identity = ""

        right_rows.append(
            {
                "row_id": right_id,
                "name": right_name,
                "identity": right_identity,
                "birth_date": right_birth,
            }
        )
        labels.append(
            {
                "entity_key": f"ENTITY-{index:04d}",
                "left_record_id": left_id,
                "right_record_id": right_id,
            }
        )

    # Near names can create extra candidates, but the invented distractor IDs have no true pair.
    for index in range(0, size, 5):
        name = names[index]
        first, last = name.split()
        right_rows.append(
            {
                "row_id": f"D-{index:04d}",
                "name": f"{first} {last}x",
                "identity": f"SYN-DISTRACTOR-{index:06d}",
                "birth_date": "1960-01-01",
            }
        )
    generator.shuffle(right_rows)
    _write_csv(directory / "left.csv", LEFT_COLUMNS, left_rows)
    _write_csv(directory / "right.csv", RIGHT_COLUMNS, right_rows)
    _write_csv(directory / "labels.csv", LABEL_COLUMNS, labels)
    (directory / "job.toml").write_text(
        """schema_version = 1
[sources.left]
path = "left.csv"
file_type = "csv"
record_id = "row_id"
[sources.right]
path = "right.csv"
file_type = "csv"
record_id = "row_id"
[[field_mappings]]
name = "name"
left_column = "name"
right_column = "name"
semantic_type = "person_name"
weight = 0.45
[[field_mappings]]
name = "identity"
left_column = "identity"
right_column = "identity"
semantic_type = "identifier"
weight = 0.35
[[field_mappings]]
name = "birth_date"
left_column = "birth_date"
right_column = "birth_date"
semantic_type = "date"
weight = 0.20
[thresholds]
automatic_match = 0.90
review = 0.70
""",
        encoding="utf-8",
    )


def main() -> None:
    """Allow independent regeneration of either labeled synthetic split."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260925)
    parser.add_argument("--size", type=int, default=80)
    args = parser.parse_args()
    generate_benchmark(args.output_directory, seed=args.seed, size=args.size)


if __name__ == "__main__":
    main()

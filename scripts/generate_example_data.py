"""Generate the small, deterministic data files used by the documented CLI example."""

from __future__ import annotations

import argparse
import csv
import random
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from openpyxl import Workbook

SEED = 20260920
DEFAULT_OUTPUT_DIRECTORY = Path(__file__).resolve().parents[1] / "examples" / "data"
_CORE_MODIFIED_PATTERN = re.compile(rb"(<dcterms:modified[^>]*>)[^<]*(</dcterms:modified>)")


@dataclass(frozen=True, slots=True)
class SyntheticPerson:
    """One invented entity used to build two intentionally inconsistent sources."""

    name: str
    synthetic_identifier: str
    birth_date: str


def _save_reproducible_workbook(workbook: Workbook, destination: Path) -> None:
    """Save an XLSX with stable ZIP metadata so identical content has an identical hash."""
    with TemporaryDirectory() as temporary_directory:
        temporary_path = Path(temporary_directory) / destination.name
        workbook.save(temporary_path)

        with (
            ZipFile(temporary_path, "r") as source,
            ZipFile(
                destination,
                "w",
                compression=ZIP_DEFLATED,
                compresslevel=9,
            ) as target,
        ):
            for filename in sorted(source.namelist()):
                metadata = ZipInfo(filename, date_time=(2026, 9, 20, 0, 0, 0))
                metadata.compress_type = ZIP_DEFLATED
                metadata.create_system = 3
                metadata.external_attr = 0o600 << 16
                content = source.read(filename)
                if filename == "docProps/core.xml":
                    content = _CORE_MODIFIED_PATTERN.sub(
                        rb"\g<1>2026-09-20T00:00:00Z\g<2>",
                        content,
                    )
                target.writestr(metadata, content)


def _synthetic_people() -> tuple[SyntheticPerson, ...]:
    generator = random.Random(SEED)
    given_names = ("Ana", "Bruno", "Camila", "Diego")
    family_names = ["Farias", "Martins", "Rocha", "Souza"]
    generator.shuffle(family_names)

    people = []
    for index, (given_name, family_name) in enumerate(
        zip(given_names, family_names, strict=True),
        start=1,
    ):
        year = generator.randint(1982, 2000)
        month = generator.randint(1, 12)
        day = generator.randint(1, 28)
        people.append(
            SyntheticPerson(
                name=f"{given_name} {family_name}",
                synthetic_identifier=f"SYN-{generator.randrange(100000, 999999)}-{index}",
                birth_date=f"{year:04d}-{month:02d}-{day:02d}",
            )
        )
    return tuple(people)


def generate_example_data(output_directory: Path = DEFAULT_OUTPUT_DIRECTORY) -> None:
    """Write one CSV and one XLSX source derived from the same invented entities."""
    output_directory.mkdir(parents=True, exist_ok=True)
    people = _synthetic_people()

    csv_path = output_directory / "customers_a.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("customer_id", "name", "tax_identifier", "date_of_birth"),
            lineterminator="\n",
        )
        writer.writeheader()
        for index, person in enumerate(people, start=1):
            writer.writerow(
                {
                    "customer_id": f"A-{index:03d}",
                    "name": person.name,
                    "tax_identifier": person.synthetic_identifier,
                    "date_of_birth": person.birth_date,
                }
            )

    workbook = Workbook()
    workbook.properties.created = datetime(2026, 9, 20)
    workbook.properties.modified = datetime(2026, 9, 20)
    worksheet = workbook.active
    worksheet.title = "Customers"
    worksheet.append(("row_id", "customer_name", "document", "birth_date"))
    for index, person in enumerate(people, start=1):
        displayed_name = person.name.upper() if index % 2 else person.name.lower()
        worksheet.append(
            (
                f"B-{index:03d}",
                displayed_name,
                person.synthetic_identifier.replace("-", ""),
                person.birth_date,
            )
        )
    _save_reproducible_workbook(workbook, output_directory / "customers_b.xlsx")


def main() -> None:
    """Generate fixtures in the default directory or an explicit test location."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=DEFAULT_OUTPUT_DIRECTORY,
        help="Directory that will receive customers_a.csv and customers_b.xlsx.",
    )
    arguments = parser.parse_args()
    generate_example_data(arguments.output_directory)


if __name__ == "__main__":
    main()

"""Tests for the reproducible synthetic CLI example data."""

import subprocess
import sys
from pathlib import Path

import pandas as pd


def _generate(output_directory: Path) -> None:
    script = Path(__file__).parents[1] / "scripts" / "generate_example_data.py"
    result = subprocess.run(
        [sys.executable, str(script), "--output-directory", str(output_directory)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_example_data_is_reproducible_and_structurally_valid(tmp_path: Path) -> None:
    first_directory = tmp_path / "first"
    second_directory = tmp_path / "second"

    _generate(first_directory)
    _generate(second_directory)

    for filename in ("customers_a.csv", "customers_b.xlsx", "name_variants.csv"):
        assert (first_directory / filename).read_bytes() == (
            second_directory / filename
        ).read_bytes()

    left = pd.read_csv(first_directory / "customers_a.csv", dtype=object)
    right = pd.read_excel(
        first_directory / "customers_b.xlsx",
        sheet_name="Customers",
        dtype=object,
    )
    variants = pd.read_csv(first_directory / "name_variants.csv", dtype=object)

    assert list(left.columns) == [
        "customer_id",
        "name",
        "tax_identifier",
        "date_of_birth",
    ]
    assert list(right.columns) == ["row_id", "customer_name", "document", "birth_date"]
    assert len(left) == len(right) == 4
    assert left["customer_id"].is_unique
    assert right["row_id"].is_unique
    assert (
        left["tax_identifier"].str.replace("-", "", regex=False).tolist()
        == right["document"].tolist()
    )
    assert list(variants.columns) == ["row_id", "customer_name", "document", "birth_date"]
    assert len(variants) == 2
    assert all(value not in left["tax_identifier"].tolist() for value in variants["document"])

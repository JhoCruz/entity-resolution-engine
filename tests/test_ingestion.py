"""Tests for CSV and XLSX source ingestion."""

from pathlib import Path

import pandas as pd
import pytest

from entity_resolution_engine.config import (
    EngineConfig,
    FieldMapping,
    FileType,
    SemanticFieldType,
    SourceConfig,
)
from entity_resolution_engine.decision import DecisionPolicy
from entity_resolution_engine.ingestion import IngestionError, load_source, load_sources
from entity_resolution_engine.validation import ValidationCode, inspect_source


def _source(
    path: Path,
    file_type: FileType = FileType.CSV,
    *,
    worksheet: str | None = None,
    delimiter: str = ",",
    encoding: str = "utf-8",
) -> SourceConfig:
    return SourceConfig(
        path=path,
        file_type=file_type,
        record_id="row_id",
        worksheet=worksheet,
        delimiter=delimiter,
        encoding=encoding,
    )


def _write_xlsx(path: Path) -> None:
    ignored = pd.DataFrame({"row_id": ["ignored"], "full_name": ["Other sheet"]})
    customers = pd.DataFrame(
        {
            "row_id": ["B-001", "B-002"],
            "full_name": [" João da Silva ", "Érica Souza"],
            "code": ["00123", "00007"],
            "note": ["N/A", ""],
        },
        dtype=object,
    )
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        ignored.to_excel(writer, sheet_name="Ignored", index=False)
        customers.to_excel(writer, sheet_name="Customers", index=False)


def test_load_csv_preserves_values_and_logical_row_numbers(tmp_path: Path) -> None:
    path = tmp_path / "customers.csv"
    content = "\n".join(
        [
            "row_id;full_name;code;note",
            "A-001; João da Silva ;00123;N/A",
            "A-002;Érica Souza;00007;",
            "",
        ]
    )
    path.write_bytes(content.encode("latin-1"))

    loaded = load_source(_source(path, delimiter=";", encoding="latin-1"))

    assert loaded.row_count == 2
    assert loaded.source_rows == (2, 3)
    assert loaded.worksheet is None
    assert loaded.data.to_dict(orient="records") == [
        {
            "row_id": "A-001",
            "full_name": " João da Silva ",
            "code": "00123",
            "note": "N/A",
        },
        {
            "row_id": "A-002",
            "full_name": "Érica Souza",
            "code": "00007",
            "note": "",
        },
    ]


def test_load_xlsx_selects_worksheet_and_preserves_values(tmp_path: Path) -> None:
    path = tmp_path / "customers.xlsx"
    _write_xlsx(path)

    loaded = load_source(_source(path, FileType.XLSX, worksheet="Customers"))

    assert loaded.row_count == 2
    assert loaded.source_rows == (2, 3)
    assert loaded.worksheet == "Customers"
    assert loaded.data.to_dict(orient="records") == [
        {
            "row_id": "B-001",
            "full_name": " João da Silva ",
            "code": "00123",
            "note": "N/A",
        },
        {
            "row_id": "B-002",
            "full_name": "Érica Souza",
            "code": "00007",
            "note": "",
        },
    ]


def test_load_xlsx_uses_first_worksheet_by_default(tmp_path: Path) -> None:
    path = tmp_path / "customers.xlsx"
    _write_xlsx(path)

    loaded = load_source(_source(path, FileType.XLSX))

    assert loaded.worksheet == "Ignored"
    assert loaded.data.loc[0, "row_id"] == "ignored"


@pytest.mark.parametrize("file_type", [FileType.CSV, FileType.XLSX])
def test_duplicate_headers_are_preserved_for_source_validation(
    tmp_path: Path, file_type: FileType
) -> None:
    path = tmp_path / f"duplicate.{file_type.value}"
    if file_type is FileType.CSV:
        path.write_text(
            "row_id,name,name\nSYN-1,Synthetic Alpha,Synthetic Beta\n", encoding="utf-8"
        )
    else:
        pd.DataFrame(
            [["SYN-1", "Synthetic Alpha", "Synthetic Beta"]],
            columns=["row_id", "name", "name"],
        ).to_excel(path, index=False, engine="openpyxl")

    loaded = load_source(_source(path, file_type))
    result = inspect_source(loaded, ("name",))

    assert list(loaded.data.columns) == ["row_id", "name", "name"]
    assert not result.is_valid
    duplicate = next(
        issue for issue in result.errors if issue.code is ValidationCode.DUPLICATE_COLUMNS
    )
    assert duplicate.columns == ("name",)


def test_csv_with_more_cells_than_headers_fails_instead_of_shifting_values(
    tmp_path: Path,
) -> None:
    path = tmp_path / "misaligned.csv"
    path.write_text("row_id,name\nSYN-1,Synthetic Alpha,Extra\n", encoding="utf-8")

    with pytest.raises(IngestionError, match=r"misaligned\.csv.*malformed"):
        load_source(_source(path))


def test_load_sources_loads_both_sides_of_engine_config(tmp_path: Path) -> None:
    left_path = tmp_path / "left.csv"
    left_path.write_text("row_id,name\nL-1,Ana\n", encoding="utf-8")
    right_path = tmp_path / "right.xlsx"
    pd.DataFrame({"row_id": ["R-1"], "customer_name": ["Ana"]}).to_excel(
        right_path,
        index=False,
        engine="openpyxl",
    )
    config = EngineConfig(
        left_source=_source(left_path),
        right_source=_source(right_path, FileType.XLSX),
        field_mappings=(
            FieldMapping(
                name="full_name",
                left_column="name",
                right_column="customer_name",
                semantic_type=SemanticFieldType.PERSON_NAME,
            ),
        ),
        decision_policy=DecisionPolicy(),
    )

    left, right = load_sources(config)

    assert left.data.loc[0, "name"] == "Ana"
    assert right.data.loc[0, "customer_name"] == "Ana"


def test_load_source_rejects_missing_file(tmp_path: Path) -> None:
    path = tmp_path / "missing.csv"

    with pytest.raises(IngestionError, match=r"missing\.csv.*does not exist"):
        load_source(_source(path))


def test_load_source_rejects_directory_path(tmp_path: Path) -> None:
    path = tmp_path / "directory.csv"
    path.mkdir()

    with pytest.raises(IngestionError, match=r"directory\.csv.*not a regular file"):
        load_source(_source(path))


def test_load_source_rejects_zero_byte_file(tmp_path: Path) -> None:
    path = tmp_path / "empty.csv"
    path.touch()

    with pytest.raises(IngestionError, match=r"empty\.csv.*file is empty"):
        load_source(_source(path))


def test_load_source_rejects_whitespace_only_csv(tmp_path: Path) -> None:
    path = tmp_path / "blank.csv"
    path.write_text("\n\n", encoding="utf-8")

    with pytest.raises(IngestionError, match=r"blank\.csv.*no columns or rows"):
        load_source(_source(path))


def test_load_source_rejects_header_only_csv(tmp_path: Path) -> None:
    path = tmp_path / "header-only.csv"
    path.write_text("row_id,name\n", encoding="utf-8")

    with pytest.raises(IngestionError, match=r"header-only\.csv.*no data rows"):
        load_source(_source(path))


def test_load_source_reports_csv_encoding_error(tmp_path: Path) -> None:
    path = tmp_path / "encoded.csv"
    path.write_bytes(b"row_id,name\nA-1,\xff\n")

    with pytest.raises(IngestionError, match=r"encoded\.csv.*encoding 'utf-8'"):
        load_source(_source(path))


@pytest.mark.parametrize("encoding", ["utf-8", "utf-16"])
def test_load_source_rejects_embedded_nul_before_it_changes_an_identifier(
    tmp_path: Path, encoding: str
) -> None:
    path = tmp_path / "nul.csv"
    path.write_text("row_id,name\nSYN-1\x00TAIL,Synthetic Alpha\n", encoding=encoding)

    with pytest.raises(IngestionError, match=r"nul\.csv.*embedded NUL character") as error:
        load_source(_source(path, encoding=encoding))

    assert "SYN-1" not in str(error.value)


def test_load_source_accepts_utf16_without_embedded_nul(tmp_path: Path) -> None:
    path = tmp_path / "encoded.csv"
    path.write_text("row_id,name\nSYN-1,Synthetic Alpha\n", encoding="utf-16")

    loaded = load_source(_source(path, encoding="utf-16"))

    assert loaded.data.loc[0, "row_id"] == "SYN-1"


def test_load_source_reports_malformed_csv(tmp_path: Path) -> None:
    path = tmp_path / "malformed.csv"
    path.write_text('row_id,name\nA-1,"unfinished\n', encoding="utf-8")

    with pytest.raises(IngestionError, match=r"malformed\.csv.*malformed"):
        load_source(_source(path))


def test_load_source_reports_missing_worksheet(tmp_path: Path) -> None:
    path = tmp_path / "customers.xlsx"
    _write_xlsx(path)

    with pytest.raises(IngestionError, match=r"customers\.xlsx.*worksheet 'Missing'.*Customers"):
        load_source(_source(path, FileType.XLSX, worksheet="Missing"))


def test_load_source_reports_corrupt_xlsx(tmp_path: Path) -> None:
    path = tmp_path / "corrupt.xlsx"
    path.write_text("not an Excel workbook", encoding="utf-8")

    with pytest.raises(IngestionError, match=r"corrupt\.xlsx.*could not be read"):
        load_source(_source(path, FileType.XLSX))

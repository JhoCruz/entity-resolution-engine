"""Tests for source schema and record identifier validation."""

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
from entity_resolution_engine.ingestion import LoadedSource
from entity_resolution_engine.validation import (
    SourceValidationError,
    ValidationCode,
    ValidationSeverity,
    inspect_source,
    inspect_sources,
    validate_source,
    validate_sources,
)


def _source(path: Path, record_id: str = "row_id") -> SourceConfig:
    return SourceConfig(path=path, file_type=FileType.CSV, record_id=record_id)


def _loaded(
    path: Path,
    data: pd.DataFrame,
    *,
    record_id: str = "row_id",
    source_rows: tuple[int, ...] | None = None,
) -> LoadedSource:
    return LoadedSource(
        source=_source(path, record_id),
        data=data,
        source_rows=source_rows or tuple(range(2, len(data) + 2)),
    )


def _config(tmp_path: Path) -> EngineConfig:
    return EngineConfig(
        left_source=_source(tmp_path / "left.csv", "left_id"),
        right_source=_source(tmp_path / "right.csv", "right_id"),
        field_mappings=(
            FieldMapping(
                name="name",
                left_column="full_name",
                right_column="legal_name",
                semantic_type=SemanticFieldType.PERSON_NAME,
            ),
        ),
        decision_policy=DecisionPolicy(),
    )


def test_validate_source_accepts_complete_unique_records(tmp_path: Path) -> None:
    data = pd.DataFrame(
        {
            "row_id": ["L-001", "L-002"],
            "full_name": ["Ana Lima", "Bruno Reis"],
        }
    )
    loaded = _loaded(tmp_path / "left.csv", data)

    validated = validate_source(loaded, ("full_name",))

    assert validated.loaded_source is loaded
    assert validated.warnings == ()
    assert validated.loaded_source.data is data


def test_unexpected_columns_are_reported_and_preserved(tmp_path: Path) -> None:
    data = pd.DataFrame(
        {
            "row_id": ["L-001"],
            "full_name": ["Ana Lima"],
            "unused_note": ["preserved"],
        }
    )
    loaded = _loaded(tmp_path / "left.csv", data)

    result = inspect_source(loaded, ("full_name",))
    validated = validate_source(loaded, ("full_name",))

    assert result.is_valid
    assert result.errors == ()
    assert len(result.warnings) == 1
    warning = result.warnings[0]
    assert warning.code is ValidationCode.UNEXPECTED_COLUMNS
    assert warning.severity is ValidationSeverity.WARNING
    assert warning.columns == ("unused_note",)
    assert validated.warnings == result.warnings
    assert validated.loaded_source.data.loc[0, "unused_note"] == "preserved"


def test_empty_source_and_missing_column_are_reported_together(tmp_path: Path) -> None:
    loaded = _loaded(
        tmp_path / "empty.csv",
        pd.DataFrame(columns=["row_id"]),
        source_rows=(),
    )

    result = inspect_source(loaded, ("full_name",))

    assert not result.is_valid
    assert {issue.code for issue in result.errors} == {
        ValidationCode.EMPTY_SOURCE,
        ValidationCode.MISSING_REQUIRED_COLUMNS,
    }
    missing = next(
        issue for issue in result.errors if issue.code is ValidationCode.MISSING_REQUIRED_COLUMNS
    )
    assert missing.columns == ("full_name",)
    assert str(loaded.source.path) in missing.message


def test_null_blank_and_duplicate_identifiers_are_reported_without_values(
    tmp_path: Path,
) -> None:
    loaded = _loaded(
        tmp_path / "mixed.csv",
        pd.DataFrame(
            {
                "row_id": ["SAFE-001", None, "   ", "SECRET-DUP", "SECRET-DUP", "SAFE-006"],
                "full_name": ["A", "B", "C", "D", "E", "F"],
            }
        ),
    )

    result = inspect_source(loaded, ("full_name",))

    assert {issue.code for issue in result.errors} == {
        ValidationCode.NULL_RECORD_IDS,
        ValidationCode.BLANK_RECORD_IDS,
        ValidationCode.DUPLICATE_RECORD_IDS,
    }
    issues = {issue.code: issue for issue in result.errors}
    assert issues[ValidationCode.NULL_RECORD_IDS].sample_rows == (3,)
    assert issues[ValidationCode.BLANK_RECORD_IDS].sample_rows == (4,)
    assert issues[ValidationCode.DUPLICATE_RECORD_IDS].sample_rows == (5, 6)
    assert all(issue.columns == ("row_id",) for issue in result.errors)

    with pytest.raises(SourceValidationError) as error:
        validate_source(loaded, ("full_name",))

    rendered = str(error.value)
    assert str(loaded.source.path) in rendered
    assert "row_id" in rendered
    assert "SECRET-DUP" not in rendered
    assert "SAFE-001" not in rendered
    assert error.value.results == (result,)


def test_duplicate_column_names_block_identifier_validation(tmp_path: Path) -> None:
    data = pd.DataFrame(
        [["L-001", "L-002", "Ana Lima"]],
        columns=["row_id", "row_id", "full_name"],
    )
    loaded = _loaded(tmp_path / "duplicate-columns.csv", data)

    result = inspect_source(loaded, ("full_name",))

    assert not result.is_valid
    duplicate = next(
        issue for issue in result.errors if issue.code is ValidationCode.DUPLICATE_COLUMNS
    )
    assert duplicate.columns == ("row_id",)
    assert duplicate.affected_count == 1
    assert not {
        ValidationCode.NULL_RECORD_IDS,
        ValidationCode.BLANK_RECORD_IDS,
        ValidationCode.DUPLICATE_RECORD_IDS,
    }.intersection(issue.code for issue in result.errors)


def test_both_sources_return_independent_problems_in_one_error(tmp_path: Path) -> None:
    config = _config(tmp_path)
    left = _loaded(
        config.left_source.path,
        pd.DataFrame({"left_id": ["L-001"]}),
        record_id="left_id",
    )
    right = _loaded(
        config.right_source.path,
        pd.DataFrame(
            {
                "right_id": ["R-001", "R-001"],
                "legal_name": ["Ana Lima", "Ana Lima"],
            }
        ),
        record_id="right_id",
    )

    results = inspect_sources(config, left, right)

    assert len(results) == 2
    assert ValidationCode.MISSING_REQUIRED_COLUMNS in {issue.code for issue in results[0].errors}
    assert ValidationCode.DUPLICATE_RECORD_IDS in {issue.code for issue in results[1].errors}

    with pytest.raises(SourceValidationError) as error:
        validate_sources(config, left, right)

    assert error.value.results == results
    assert str(config.left_source.path) in str(error.value)
    assert str(config.right_source.path) in str(error.value)
    assert "R-001" not in str(error.value)


def test_validate_sources_returns_both_validated_sources(tmp_path: Path) -> None:
    config = _config(tmp_path)
    left = _loaded(
        config.left_source.path,
        pd.DataFrame({"left_id": ["L-001"], "full_name": ["Ana Lima"]}),
        record_id="left_id",
    )
    right = _loaded(
        config.right_source.path,
        pd.DataFrame({"right_id": ["R-001"], "legal_name": ["Ana Lima"]}),
        record_id="right_id",
    )

    validated_left, validated_right = validate_sources(config, left, right)

    assert validated_left.loaded_source is left
    assert validated_right.loaded_source is right


def test_identifier_row_samples_are_bounded(tmp_path: Path) -> None:
    sensitive_identifier = "NEVER-PRINT-THIS"
    loaded = _loaded(
        tmp_path / "large-duplicate.csv",
        pd.DataFrame(
            {
                "row_id": [sensitive_identifier] * 12,
                "full_name": [f"Synthetic {index}" for index in range(12)],
            }
        ),
    )

    result = inspect_source(loaded, ("full_name",))
    duplicate = next(
        issue for issue in result.errors if issue.code is ValidationCode.DUPLICATE_RECORD_IDS
    )

    assert duplicate.affected_count == 12
    assert duplicate.sample_rows == tuple(range(2, 12))
    assert "(+2 more)" in duplicate.message
    assert sensitive_identifier not in duplicate.message

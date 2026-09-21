"""Tests for auditable baseline normalization."""

from collections.abc import Callable
from pathlib import Path

import pandas as pd
import pytest

from entity_resolution_engine.config import (
    EngineConfig,
    FieldMapping,
    FileType,
    SemanticFieldType,
    SourceConfig,
    load_config,
)
from entity_resolution_engine.decision import DecisionPolicy
from entity_resolution_engine.ingestion import LoadedSource, load_sources
from entity_resolution_engine.normalization import (
    SOURCE_RECORD_ID_COLUMN,
    SOURCE_ROW_COLUMN,
    NormalizationStep,
    NormalizedValue,
    normalize_identifier,
    normalize_person_name,
    normalize_semantic_value,
    normalize_sources,
    normalize_text,
)
from entity_resolution_engine.validation import validate_sources


@pytest.mark.parametrize(
    ("original", "expected", "steps"),
    [
        (
            "  \uff2a\uff2fÃ\uff2f\t\uff24\uff21—\uff33\uff29\uff2c\uff36\uff21  ",
            "joão da silva",
            (
                NormalizationStep.UNICODE_NFKC,
                NormalizationStep.CASE_FOLD,
                NormalizationStep.PUNCTUATION_TO_SPACE,
                NormalizationStep.WHITESPACE_COLLAPSE,
            ),
        ),
        ("Straße", "strasse", (NormalizationStep.CASE_FOLD,)),
        (
            "D'Ávila-Souza",
            "d ávila souza",
            (
                NormalizationStep.CASE_FOLD,
                NormalizationStep.PUNCTUATION_TO_SPACE,
            ),
        ),
        ("ﬁle", "file", (NormalizationStep.UNICODE_NFKC,)),
        ("  two   spaces  ", "two spaces", (NormalizationStep.WHITESPACE_COLLAPSE,)),
        ("C++", "c++", (NormalizationStep.CASE_FOLD,)),
        (
            "---",
            "",
            (
                NormalizationStep.PUNCTUATION_TO_SPACE,
                NormalizationStep.WHITESPACE_COLLAPSE,
            ),
        ),
        (12345, "12345", (NormalizationStep.COERCE_TO_TEXT,)),
        (
            True,
            "true",
            (NormalizationStep.COERCE_TO_TEXT, NormalizationStep.CASE_FOLD),
        ),
    ],
)
def test_normalize_text_records_each_applied_transformation(
    original: object,
    expected: str,
    steps: tuple[NormalizationStep, ...],
) -> None:
    result = normalize_text(original)

    assert result.original is original
    assert result.normalized == expected
    assert result.transformations == steps


@pytest.mark.parametrize("missing", [None, pd.NA, float("nan")])
def test_normalize_text_preserves_missing_values(missing: object) -> None:
    result = normalize_text(missing)

    assert result.original is missing
    assert result.normalized is None
    assert result.transformations == ()


@pytest.mark.parametrize("composite", [["not", "scalar"], {"nested": "value"}])
def test_normalize_text_rejects_composite_cell_values(composite: object) -> None:
    with pytest.raises(TypeError, match="scalar values only"):
        normalize_text(composite)


@pytest.mark.parametrize(
    "original",
    ["Already normalized", "  Mixed—Input  ", "Straße", 12345, None],
)
def test_normalize_text_is_idempotent(original: object) -> None:
    first = normalize_text(original)
    second = normalize_text(first.normalized)

    assert second.normalized == first.normalized
    assert second.transformations == ()


@pytest.mark.parametrize(
    ("original", "expected", "steps"),
    [
        (
            "  João D'Ávila-Souza  ",
            "joao d avila souza",
            (
                NormalizationStep.CASE_FOLD,
                NormalizationStep.PUNCTUATION_TO_SPACE,
                NormalizationStep.WHITESPACE_COLLAPSE,
                NormalizationStep.DIACRITICS_REMOVED,
            ),
        ),
        (
            "Jose\u0301",
            "jose",
            (
                NormalizationStep.UNICODE_NFKC,
                NormalizationStep.CASE_FOLD,
                NormalizationStep.DIACRITICS_REMOVED,
            ),
        ),
        ("ana maria", "ana maria", ()),
        (None, None, ()),
    ],
)
def test_normalize_person_name_removes_diacritics_after_baseline(
    original: object,
    expected: str | None,
    steps: tuple[NormalizationStep, ...],
) -> None:
    result = normalize_person_name(original)

    assert result.original is original
    assert result.normalized == expected
    assert result.transformations == steps


@pytest.mark.parametrize(
    ("original", "expected", "steps"),
    [
        (
            "  SYN-000.123/AB  ",
            "syn000123ab",
            (
                NormalizationStep.CASE_FOLD,
                NormalizationStep.PUNCTUATION_TO_SPACE,
                NormalizationStep.WHITESPACE_COLLAPSE,
                NormalizationStep.NON_ALPHANUMERIC_REMOVED,
            ),
        ),
        ("000123", "000123", ()),
        (123, "123", (NormalizationStep.COERCE_TO_TEXT,)),
        (
            "A+B C",
            "abc",
            (
                NormalizationStep.CASE_FOLD,
                NormalizationStep.NON_ALPHANUMERIC_REMOVED,
            ),
        ),
        (
            "---",
            "",
            (
                NormalizationStep.PUNCTUATION_TO_SPACE,
                NormalizationStep.WHITESPACE_COLLAPSE,
            ),
        ),
        (None, None, ()),
    ],
)
def test_normalize_identifier_removes_formatting_and_preserves_leading_zeros(
    original: object,
    expected: str | None,
    steps: tuple[NormalizationStep, ...],
) -> None:
    result = normalize_identifier(original)

    assert result.original is original
    assert result.normalized == expected
    assert result.transformations == steps


@pytest.mark.parametrize(
    ("normalizer", "original"),
    [
        (normalize_person_name, "  João D'Ávila-Souza  "),
        (normalize_identifier, "  SYN-000.123/AB  "),
    ],
)
def test_semantic_normalizers_are_idempotent(
    normalizer: Callable[[object], NormalizedValue],
    original: object,
) -> None:
    first = normalizer(original)
    second = normalizer(first.normalized)

    assert second.normalized == first.normalized
    assert second.transformations == ()


@pytest.mark.parametrize(
    "semantic_type",
    [
        SemanticFieldType.TEXT,
        SemanticFieldType.DATE,
        SemanticFieldType.EMAIL,
        SemanticFieldType.PHONE,
    ],
)
def test_unimplemented_semantic_types_use_the_baseline(
    semantic_type: SemanticFieldType,
) -> None:
    result = normalize_semantic_value("Á+B", semantic_type)

    assert result.normalized == "á+b"
    assert result.transformations == (NormalizationStep.CASE_FOLD,)


def _source(path: Path, record_id: str) -> SourceConfig:
    return SourceConfig(path=path, file_type=FileType.CSV, record_id=record_id)


def _config(tmp_path: Path) -> EngineConfig:
    return EngineConfig(
        left_source=_source(tmp_path / "left.csv", "left_id"),
        right_source=_source(tmp_path / "right.csv", "right_id"),
        field_mappings=(
            FieldMapping(
                name="full_name",
                left_column="name",
                right_column="customer_name",
                semantic_type=SemanticFieldType.PERSON_NAME,
            ),
            FieldMapping(
                name="tax_id",
                left_column="tax_identifier",
                right_column="document",
                semantic_type=SemanticFieldType.IDENTIFIER,
            ),
        ),
        decision_policy=DecisionPolicy(),
    )


def _loaded(source: SourceConfig, data: pd.DataFrame) -> LoadedSource:
    return LoadedSource(
        source=source,
        data=data,
        source_rows=tuple(range(2, len(data) + 2)),
    )


def test_normalize_sources_preserves_originals_and_provenance(tmp_path: Path) -> None:
    config = _config(tmp_path)
    left_data = pd.DataFrame(
        {
            "left_id": ["L-001", "L-002"],
            "name": ["  ÁNA—SOUZA ", "Bruno Martins"],
            "tax_identifier": ["SYN-001", "000-002"],
        }
    )
    right_data = pd.DataFrame(
        {
            "right_id": ["R-001", "R-002"],
            "customer_name": ["ana souza", "BRUNO MARTINS"],
            "document": ["SYN001", "000002"],
        }
    )
    left_before = left_data.copy(deep=True)
    right_before = right_data.copy(deep=True)
    loaded_left = _loaded(config.left_source, left_data)
    loaded_right = _loaded(config.right_source, right_data)
    validated_left, validated_right = validate_sources(config, loaded_left, loaded_right)

    normalized_left, normalized_right = normalize_sources(
        config,
        validated_left,
        validated_right,
    )

    pd.testing.assert_frame_equal(left_data, left_before)
    pd.testing.assert_frame_equal(right_data, right_before)
    assert normalized_left.validated_source is validated_left
    assert normalized_right.validated_source is validated_right
    assert normalized_left.row_count == normalized_right.row_count == 2
    assert normalized_left.data.columns.tolist() == [
        SOURCE_RECORD_ID_COLUMN,
        SOURCE_ROW_COLUMN,
        "full_name_original",
        "full_name_normalized",
        "full_name_transformations",
        "tax_id_original",
        "tax_id_normalized",
        "tax_id_transformations",
    ]
    assert normalized_left.data[SOURCE_RECORD_ID_COLUMN].tolist() == ["L-001", "L-002"]
    assert normalized_left.data[SOURCE_ROW_COLUMN].tolist() == [2, 3]
    assert normalized_left.data["full_name_original"].tolist() == [
        "  ÁNA—SOUZA ",
        "Bruno Martins",
    ]
    assert normalized_left.data["full_name_normalized"].tolist() == [
        "ana souza",
        "bruno martins",
    ]
    assert normalized_right.data["full_name_normalized"].tolist() == [
        "ana souza",
        "bruno martins",
    ]
    assert normalized_left.data["tax_id_normalized"].tolist() == ["syn001", "000002"]
    assert normalized_right.data["tax_id_normalized"].tolist() == ["syn001", "000002"]
    assert normalized_left.data.loc[0, "full_name_transformations"] == (
        "case_fold",
        "punctuation_to_space",
        "whitespace_collapse",
        "diacritics_removed",
    )
    assert normalized_left.data.loc[0, "tax_id_transformations"] == (
        "case_fold",
        "punctuation_to_space",
        "non_alphanumeric_removed",
    )
    assert [field.name for field in normalized_left.fields] == ["full_name", "tax_id"]
    assert normalized_left.fields[0].semantic_type is SemanticFieldType.PERSON_NAME


def test_documented_csv_xlsx_pipeline_normalizes_both_sources() -> None:
    config = load_config("examples/basic-job.toml")
    loaded_left, loaded_right = load_sources(config)
    validated_left, validated_right = validate_sources(config, loaded_left, loaded_right)

    normalized_left, normalized_right = normalize_sources(
        config,
        validated_left,
        validated_right,
    )

    assert normalized_left.row_count == normalized_right.row_count == 4
    assert (
        normalized_left.data["full_name_normalized"].tolist()
        == normalized_right.data["full_name_normalized"].tolist()
    )
    assert normalized_left.data[SOURCE_RECORD_ID_COLUMN].tolist() == [
        "A-001",
        "A-002",
        "A-003",
        "A-004",
    ]
    assert normalized_right.data[SOURCE_RECORD_ID_COLUMN].tolist() == [
        "B-001",
        "B-002",
        "B-003",
        "B-004",
    ]

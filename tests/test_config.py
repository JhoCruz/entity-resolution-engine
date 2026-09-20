"""Tests for typed job configuration contracts."""

from dataclasses import replace
from pathlib import Path

import pytest

from entity_resolution_engine.config import (
    ConfigurationError,
    EngineConfig,
    FieldMapping,
    FileType,
    SemanticFieldType,
    SourceConfig,
    load_config,
)
from entity_resolution_engine.decision import DecisionPolicy

VALID_CONFIG = """
schema_version = 1

[sources.left]
path = "inputs/customers.csv"
file_type = "csv"
record_id = "customer_id"
delimiter = ";"
encoding = "latin-1"

[sources.right]
path = "inputs/registry.xlsx"
file_type = "xlsx"
record_id = "row_id"
worksheet = "Customers"

[[field_mappings]]
name = "full_name"
left_column = "name"
right_column = "customer_name"
semantic_type = "person_name"
weight = 0.6

[[field_mappings]]
name = "tax_id"
left_column = "tax_identifier"
right_column = "document"
semantic_type = "identifier"
weight = 1.0

[thresholds]
automatic_match = 0.9
review = 0.7
""".strip()

INVALID_SOURCES_TYPE_CONFIG = """
schema_version = 1
sources = "invalid"
field_mappings = []

[thresholds]
automatic_match = 0.9
review = 0.7
""".strip()

INVALID_FIELD_MAPPINGS_TYPE_CONFIG = """
schema_version = 1
field_mappings = 1

[sources.left]
path = "left.csv"
file_type = "csv"
record_id = "left_id"

[sources.right]
path = "right.csv"
file_type = "csv"
record_id = "right_id"

[thresholds]
automatic_match = 0.9
review = 0.7
""".strip()


def _write_config(tmp_path: Path, content: str = VALID_CONFIG) -> Path:
    path = tmp_path / "job.toml"
    path.write_text(content, encoding="utf-8")
    return path


def _source(path: str, record_id: str) -> SourceConfig:
    return SourceConfig(path=Path(path), file_type=FileType.CSV, record_id=record_id)


def _mapping(
    name: str = "full_name",
    left_column: str = "name",
    right_column: str = "customer_name",
) -> FieldMapping:
    return FieldMapping(
        name=name,
        left_column=left_column,
        right_column=right_column,
        semantic_type=SemanticFieldType.PERSON_NAME,
    )


def _engine_config(*mappings: FieldMapping, schema_version: int = 1) -> EngineConfig:
    return EngineConfig(
        left_source=_source("left.csv", "left_row_id"),
        right_source=_source("right.csv", "right_row_id"),
        field_mappings=mappings,
        decision_policy=DecisionPolicy(),
        schema_version=schema_version,
    )


def test_load_config_returns_deterministic_typed_contracts(tmp_path: Path) -> None:
    path = _write_config(tmp_path)

    first = load_config(path)
    second = load_config(path)

    assert first == second
    assert first.schema_version == 1
    assert first.left_source == SourceConfig(
        path=(tmp_path / "inputs/customers.csv").resolve(),
        file_type=FileType.CSV,
        record_id="customer_id",
        delimiter=";",
        encoding="latin-1",
    )
    assert first.right_source.worksheet == "Customers"
    assert first.field_mappings[0] == FieldMapping(
        name="full_name",
        left_column="name",
        right_column="customer_name",
        semantic_type=SemanticFieldType.PERSON_NAME,
        weight=0.6,
    )
    assert first.decision_policy == DecisionPolicy(
        automatic_match_threshold=0.9,
        review_threshold=0.7,
    )


def test_mapping_weight_defaults_to_one(tmp_path: Path) -> None:
    config = VALID_CONFIG.replace("weight = 0.6\n", "", 1)

    loaded = load_config(_write_config(tmp_path, config))

    assert loaded.field_mappings[0].weight == 1.0


def test_source_rejects_extension_that_disagrees_with_file_type() -> None:
    with pytest.raises(ConfigurationError, match=r"must use \.csv"):
        SourceConfig(
            path=Path("customers.xlsx"),
            file_type=FileType.CSV,
            record_id="row_id",
        )


def test_source_rejects_worksheet_for_csv() -> None:
    with pytest.raises(ConfigurationError, match="only be set for an xlsx"):
        SourceConfig(
            path=Path("customers.csv"),
            file_type=FileType.CSV,
            record_id="row_id",
            worksheet="Sheet 1",
        )


@pytest.mark.parametrize("delimiter", ["", "||", "\n"])
def test_source_rejects_invalid_csv_delimiter(delimiter: str) -> None:
    with pytest.raises(ConfigurationError, match="delimiter"):
        SourceConfig(
            path=Path("customers.csv"),
            file_type=FileType.CSV,
            record_id="row_id",
            delimiter=delimiter,
        )


def test_source_rejects_unknown_text_encoding() -> None:
    with pytest.raises(ConfigurationError, match="Unknown text encoding"):
        SourceConfig(
            path=Path("customers.csv"),
            file_type=FileType.CSV,
            record_id="row_id",
            encoding="not-a-real-encoding",
        )


def test_config_rejects_csv_options_for_xlsx(tmp_path: Path) -> None:
    config = VALID_CONFIG.replace(
        'worksheet = "Customers"',
        'worksheet = "Customers"\ndelimiter = ";"',
    )

    with pytest.raises(ConfigurationError, match="can only be set for a csv"):
        load_config(_write_config(tmp_path, config))


def test_xlsx_source_rejects_custom_csv_options() -> None:
    with pytest.raises(ConfigurationError, match="only be customized for csv"):
        SourceConfig(
            path=Path("customers.xlsx"),
            file_type=FileType.XLSX,
            record_id="row_id",
            delimiter=";",
        )


@pytest.mark.parametrize("record_id", ["", " row_id", "row_id "])
def test_source_rejects_invalid_record_identifier(record_id: str) -> None:
    with pytest.raises(ConfigurationError, match="record_id"):
        SourceConfig(path=Path("customers.csv"), file_type=FileType.CSV, record_id=record_id)


@pytest.mark.parametrize("name", ["FullName", "full-name", "1_name", ""])
def test_mapping_rejects_invalid_logical_name(name: str) -> None:
    with pytest.raises(ConfigurationError, match="Field mapping name"):
        _mapping(name=name)


@pytest.mark.parametrize(
    ("left_column", "right_column", "message"),
    [
        ("", "customer_name", "left_column"),
        (" name", "customer_name", "left_column"),
        ("name", "", "right_column"),
        ("name", "customer_name ", "right_column"),
    ],
)
def test_mapping_rejects_invalid_column_names(
    left_column: str, right_column: str, message: str
) -> None:
    with pytest.raises(ConfigurationError, match=message):
        _mapping(left_column=left_column, right_column=right_column)


@pytest.mark.parametrize("weight", [0.0, -1.0, float("inf"), float("nan")])
def test_mapping_rejects_invalid_weights(weight: float) -> None:
    with pytest.raises(ConfigurationError, match="finite number greater than 0"):
        FieldMapping(
            name="full_name",
            left_column="name",
            right_column="customer_name",
            semantic_type=SemanticFieldType.PERSON_NAME,
            weight=weight,
        )


@pytest.mark.parametrize(
    ("first", "second", "duplicate_attribute"),
    [
        (_mapping(), _mapping(left_column="legal_name", right_column="name_2"), "name"),
        (_mapping(), _mapping(name="alias", right_column="name_2"), "left_column"),
        (_mapping(), _mapping(name="alias", left_column="alias"), "right_column"),
    ],
)
def test_engine_config_rejects_duplicate_mappings(
    first: FieldMapping, second: FieldMapping, duplicate_attribute: str
) -> None:
    with pytest.raises(ConfigurationError, match=duplicate_attribute):
        _engine_config(first, second)


def test_engine_config_requires_at_least_one_mapping() -> None:
    with pytest.raises(ConfigurationError, match="at least one"):
        _engine_config()


def test_engine_config_rejects_unknown_schema_version() -> None:
    with pytest.raises(ConfigurationError, match="Unsupported schema_version 2"):
        _engine_config(_mapping(), schema_version=2)


@pytest.mark.parametrize(
    "mapping",
    [
        _mapping(left_column="left_row_id"),
        _mapping(right_column="right_row_id"),
    ],
)
def test_engine_config_keeps_record_ids_out_of_matching_fields(mapping: FieldMapping) -> None:
    with pytest.raises(ConfigurationError, match="cannot reuse"):
        _engine_config(mapping)


def test_load_config_reports_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="Cannot read configuration"):
        load_config(tmp_path / "missing.toml")


def test_load_config_reports_invalid_toml(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="Invalid TOML"):
        load_config(_write_config(tmp_path, "not = [valid"))


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (VALID_CONFIG + "\nunexpected = true", "Unknown key"),
        (VALID_CONFIG.replace("schema_version = 1", 'schema_version = "1"'), "must be an integer"),
        (INVALID_SOURCES_TYPE_CONFIG, "sources must be a table"),
        (VALID_CONFIG.replace('file_type = "csv"', 'file_type = "json"', 1), "must be one of"),
        (VALID_CONFIG.replace('record_id = "customer_id"', 'record_id = ""', 1), "record_id"),
        (INVALID_FIELD_MAPPINGS_TYPE_CONFIG, "array of tables"),
        (
            VALID_CONFIG.replace('semantic_type = "person_name"', 'semantic_type = "money"'),
            "must be one of",
        ),
        (VALID_CONFIG.replace("weight = 0.6", 'weight = "heavy"'), "weight must be a number"),
        (
            VALID_CONFIG.replace("automatic_match = 0.9", "automatic_match = true"),
            "must be a number",
        ),
        (VALID_CONFIG.replace("review = 0.7", "review = 0.95"), "Invalid thresholds"),
    ],
)
def test_load_config_returns_actionable_errors(tmp_path: Path, content: str, message: str) -> None:
    with pytest.raises(ConfigurationError, match=message):
        load_config(_write_config(tmp_path, content))


def test_dataclass_replace_preserves_validation() -> None:
    mapping = _mapping()

    with pytest.raises(ConfigurationError, match="greater than 0"):
        replace(mapping, weight=0.0)

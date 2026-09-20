"""Typed configuration contracts for a two-source resolution job."""

from __future__ import annotations

import math
import re
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import cast

from entity_resolution_engine.decision import DecisionPolicy


class ConfigurationError(ValueError):
    """Raised when a configuration cannot describe an unambiguous job."""


class FileType(StrEnum):
    """Tabular file types accepted by the ingestion milestone."""

    CSV = "csv"
    XLSX = "xlsx"


class SemanticFieldType(StrEnum):
    """Meaning of a mapped field, used by future normalization and scoring."""

    TEXT = "text"
    PERSON_NAME = "person_name"
    IDENTIFIER = "identifier"
    DATE = "date"
    EMAIL = "email"
    PHONE = "phone"


_LOGICAL_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
_SUPPORTED_SUFFIXES = {
    FileType.CSV: frozenset({".csv"}),
    FileType.XLSX: frozenset({".xlsx"}),
}


def _validate_exact_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ConfigurationError(f"{label} must be a non-empty string.")
    if value != value.strip():
        raise ConfigurationError(f"{label} must not have leading or trailing whitespace.")
    return value


@dataclass(frozen=True, slots=True)
class SourceConfig:
    """Location and row identifier for one tabular source."""

    path: Path
    file_type: FileType
    record_id: str
    worksheet: str | None = None

    def __post_init__(self) -> None:
        _validate_exact_text(self.record_id, "record_id")
        if self.path.suffix.lower() not in _SUPPORTED_SUFFIXES[self.file_type]:
            expected = ", ".join(sorted(_SUPPORTED_SUFFIXES[self.file_type]))
            raise ConfigurationError(
                f"Source path '{self.path}' must use {expected} for file type "
                f"'{self.file_type.value}'."
            )
        if self.worksheet is not None:
            _validate_exact_text(self.worksheet, "worksheet")
            if self.file_type is not FileType.XLSX:
                raise ConfigurationError("worksheet can only be set for an xlsx source.")


@dataclass(frozen=True, slots=True)
class FieldMapping:
    """Corresponding columns from the left and right sources."""

    name: str
    left_column: str
    right_column: str
    semantic_type: SemanticFieldType
    weight: float = 1.0

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not _LOGICAL_NAME_PATTERN.fullmatch(self.name):
            raise ConfigurationError(
                "Field mapping name must start with a lowercase letter and contain only "
                "lowercase letters, numbers, and underscores."
            )
        _validate_exact_text(self.left_column, "left_column")
        _validate_exact_text(self.right_column, "right_column")
        if isinstance(self.weight, bool) or not isinstance(self.weight, (int, float)):
            raise ConfigurationError("Field mapping weight must be a finite number greater than 0.")
        normalized_weight = float(self.weight)
        if not math.isfinite(normalized_weight) or normalized_weight <= 0:
            raise ConfigurationError("Field mapping weight must be a finite number greater than 0.")
        object.__setattr__(self, "weight", normalized_weight)


def _ensure_unique(values: Sequence[str], attribute: str) -> None:
    first_index: dict[str, int] = {}
    for index, value in enumerate(values):
        if value in first_index:
            previous = first_index[value]
            raise ConfigurationError(
                f"field_mappings[{index}].{attribute} duplicates "
                f"field_mappings[{previous}].{attribute} ('{value}')."
            )
        first_index[value] = index


@dataclass(frozen=True, slots=True)
class EngineConfig:
    """Complete, validated configuration for one two-source resolution job."""

    left_source: SourceConfig
    right_source: SourceConfig
    field_mappings: tuple[FieldMapping, ...]
    decision_policy: DecisionPolicy
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ConfigurationError(
                f"Unsupported schema_version {self.schema_version}; expected schema_version 1."
            )
        if not self.field_mappings:
            raise ConfigurationError("field_mappings must contain at least one mapping.")

        _ensure_unique([item.name for item in self.field_mappings], "name")
        _ensure_unique([item.left_column for item in self.field_mappings], "left_column")
        _ensure_unique([item.right_column for item in self.field_mappings], "right_column")

        for index, mapping in enumerate(self.field_mappings):
            if mapping.left_column == self.left_source.record_id:
                raise ConfigurationError(
                    f"field_mappings[{index}].left_column cannot reuse the left record_id "
                    f"column ('{mapping.left_column}')."
                )
            if mapping.right_column == self.right_source.record_id:
                raise ConfigurationError(
                    f"field_mappings[{index}].right_column cannot reuse the right record_id "
                    f"column ('{mapping.right_column}')."
                )


Table = dict[str, object]


def _reject_unknown_keys(table: Mapping[str, object], allowed: set[str], location: str) -> None:
    unknown = sorted(set(table) - allowed)
    if unknown:
        rendered = ", ".join(repr(key) for key in unknown)
        raise ConfigurationError(f"Unknown key(s) in {location}: {rendered}.")


def _required_table(table: Mapping[str, object], key: str, location: str) -> Table:
    value = table.get(key)
    if not isinstance(value, dict):
        raise ConfigurationError(f"{location}.{key} must be a table.")
    return cast(Table, value)


def _required_string(table: Mapping[str, object], key: str, location: str) -> str:
    value = table.get(key)
    if not isinstance(value, str) or not value:
        raise ConfigurationError(f"{location}.{key} must be a non-empty string.")
    return value


def _optional_string(table: Mapping[str, object], key: str, location: str) -> str | None:
    if key not in table:
        return None
    return _required_string(table, key, location)


def _required_integer(table: Mapping[str, object], key: str, location: str) -> int:
    value = table.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigurationError(f"{location}.{key} must be an integer.")
    return value


def _required_number(table: Mapping[str, object], key: str, location: str) -> float:
    value = table.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigurationError(f"{location}.{key} must be a number.")
    return float(value)


def _optional_number(table: Mapping[str, object], key: str, location: str, default: float) -> float:
    if key not in table:
        return default
    return _required_number(table, key, location)


def _required_enum[EnumType: StrEnum](
    table: Mapping[str, object],
    key: str,
    location: str,
    enum_type: type[EnumType],
) -> EnumType:
    value = _required_string(table, key, location)
    try:
        return enum_type(value)
    except ValueError as error:
        allowed = ", ".join(repr(item.value) for item in enum_type)
        raise ConfigurationError(
            f"{location}.{key} must be one of: {allowed}; received {value!r}."
        ) from error


def _resolve_source_path(raw_path: str, config_directory: Path) -> Path:
    source_path = Path(raw_path)
    if not source_path.is_absolute():
        source_path = config_directory / source_path
    return source_path.resolve()


def _parse_source(table: Table, location: str, config_directory: Path) -> SourceConfig:
    _reject_unknown_keys(
        table,
        {"path", "file_type", "record_id", "worksheet"},
        location,
    )
    file_type = _required_enum(table, "file_type", location, FileType)
    try:
        return SourceConfig(
            path=_resolve_source_path(_required_string(table, "path", location), config_directory),
            file_type=file_type,
            record_id=_required_string(table, "record_id", location),
            worksheet=_optional_string(table, "worksheet", location),
        )
    except ConfigurationError as error:
        raise ConfigurationError(f"Invalid {location}: {error}") from error


def _parse_field_mapping(table: Table, index: int) -> FieldMapping:
    location = f"field_mappings[{index}]"
    _reject_unknown_keys(
        table,
        {"name", "left_column", "right_column", "semantic_type", "weight"},
        location,
    )
    try:
        return FieldMapping(
            name=_required_string(table, "name", location),
            left_column=_required_string(table, "left_column", location),
            right_column=_required_string(table, "right_column", location),
            semantic_type=_required_enum(table, "semantic_type", location, SemanticFieldType),
            weight=_optional_number(table, "weight", location, 1.0),
        )
    except ConfigurationError as error:
        raise ConfigurationError(f"Invalid {location}: {error}") from error


def _parse_field_mappings(root: Table) -> tuple[FieldMapping, ...]:
    value = root.get("field_mappings")
    if not isinstance(value, list):
        raise ConfigurationError("configuration.field_mappings must be an array of tables.")

    mappings: list[FieldMapping] = []
    for index, item in enumerate(cast(list[object], value)):
        if not isinstance(item, dict):
            raise ConfigurationError(f"field_mappings[{index}] must be a table.")
        mappings.append(_parse_field_mapping(cast(Table, item), index))
    return tuple(mappings)


def _parse_decision_policy(table: Table) -> DecisionPolicy:
    location = "thresholds"
    _reject_unknown_keys(
        table,
        {"automatic_match", "review"},
        location,
    )
    try:
        return DecisionPolicy(
            automatic_match_threshold=_required_number(table, "automatic_match", location),
            review_threshold=_required_number(table, "review", location),
        )
    except ValueError as error:
        raise ConfigurationError(f"Invalid thresholds: {error}") from error


def load_config(path: str | Path) -> EngineConfig:
    """Load and validate a TOML job configuration.

    Relative source paths are resolved from the configuration file's directory,
    so the same project checkout produces the same locations from any working directory.
    """
    config_path = Path(path).resolve()
    try:
        with config_path.open("rb") as handle:
            root = cast(Table, tomllib.load(handle))
    except tomllib.TOMLDecodeError as error:
        raise ConfigurationError(f"Invalid TOML in '{config_path}': {error}") from error
    except OSError as error:
        detail = error.strerror or str(error)
        raise ConfigurationError(f"Cannot read configuration '{config_path}': {detail}.") from error

    _reject_unknown_keys(
        root,
        {"schema_version", "sources", "field_mappings", "thresholds"},
        "configuration",
    )
    sources = _required_table(root, "sources", "configuration")
    _reject_unknown_keys(sources, {"left", "right"}, "sources")

    config = EngineConfig(
        schema_version=_required_integer(root, "schema_version", "configuration"),
        left_source=_parse_source(
            _required_table(sources, "left", "sources"),
            "sources.left",
            config_path.parent,
        ),
        right_source=_parse_source(
            _required_table(sources, "right", "sources"),
            "sources.right",
            config_path.parent,
        ),
        field_mappings=_parse_field_mappings(root),
        decision_policy=_parse_decision_policy(
            _required_table(root, "thresholds", "configuration")
        ),
    )
    return config


__all__ = [
    "ConfigurationError",
    "EngineConfig",
    "FieldMapping",
    "FileType",
    "SemanticFieldType",
    "SourceConfig",
    "load_config",
]

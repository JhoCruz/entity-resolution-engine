"""Validate loaded source schemas and row identifiers before normalization."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from entity_resolution_engine.config import EngineConfig
from entity_resolution_engine.ingestion import LoadedSource

_ROW_SAMPLE_LIMIT = 10


class ValidationSeverity(StrEnum):
    """Whether an issue blocks later pipeline stages."""

    ERROR = "error"
    WARNING = "warning"


class ValidationCode(StrEnum):
    """Stable machine-readable source validation outcomes."""

    EMPTY_SOURCE = "empty_source"
    MISSING_REQUIRED_COLUMNS = "missing_required_columns"
    DUPLICATE_COLUMNS = "duplicate_columns"
    UNEXPECTED_COLUMNS = "unexpected_columns"
    NULL_RECORD_IDS = "null_record_ids"
    BLANK_RECORD_IDS = "blank_record_ids"
    DUPLICATE_RECORD_IDS = "duplicate_record_ids"


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """One validation finding without exposing source field values."""

    code: ValidationCode
    severity: ValidationSeverity
    source_path: Path
    message: str
    columns: tuple[str, ...] = ()
    affected_count: int = 0
    sample_rows: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """All independently detectable findings for one loaded source."""

    loaded_source: LoadedSource
    issues: tuple[ValidationIssue, ...]

    @property
    def errors(self) -> tuple[ValidationIssue, ...]:
        """Return findings that block later processing."""
        return tuple(issue for issue in self.issues if issue.severity is ValidationSeverity.ERROR)

    @property
    def warnings(self) -> tuple[ValidationIssue, ...]:
        """Return non-blocking findings retained for inspection."""
        return tuple(issue for issue in self.issues if issue.severity is ValidationSeverity.WARNING)

    @property
    def is_valid(self) -> bool:
        """Return whether the source may enter later pipeline stages."""
        return not self.errors


@dataclass(frozen=True, slots=True)
class ValidatedSource:
    """A loaded source that passed every blocking validation rule."""

    loaded_source: LoadedSource
    warnings: tuple[ValidationIssue, ...] = ()


class SourceValidationError(ValueError):
    """Raised with complete validation results when any source is invalid."""

    def __init__(self, results: tuple[ValidationResult, ...]) -> None:
        self.results = results
        messages = [issue.message for result in results for issue in result.errors]
        rendered = "\n- ".join(messages)
        super().__init__(f"Source validation failed:\n- {rendered}")


def _format_columns(columns: tuple[str, ...]) -> str:
    return ", ".join(repr(column) for column in columns)


def _source_rows(loaded: LoadedSource, positions: list[int]) -> tuple[int, ...]:
    return tuple(loaded.source_rows[position] for position in positions)


def _sample_rows(rows: tuple[int, ...]) -> tuple[int, ...]:
    return rows[:_ROW_SAMPLE_LIMIT]


def _format_row_context(rows: tuple[int, ...]) -> str:
    sampled = _sample_rows(rows)
    rendered = ", ".join(str(row) for row in sampled)
    if len(rows) > len(sampled):
        rendered += f" (+{len(rows) - len(sampled)} more)"
    return rendered


def _identifier_issues(loaded: LoadedSource) -> list[ValidationIssue]:
    path = loaded.source.path
    column = loaded.source.record_id
    identifiers = loaded.data[column]

    null_flags = identifiers.isna().tolist()
    null_positions = [position for position, flag in enumerate(null_flags) if flag]
    blank_positions = [
        position
        for position, value in enumerate(identifiers.tolist())
        if not null_flags[position] and isinstance(value, str) and not value.strip()
    ]
    invalid_positions = set(null_positions) | set(blank_positions)
    valid_positions = [
        position for position in range(len(identifiers)) if position not in invalid_positions
    ]
    valid_identifiers = identifiers.take(valid_positions)
    duplicate_flags = valid_identifiers.duplicated(keep=False).tolist()
    duplicate_positions = [
        position
        for position, is_duplicate in zip(valid_positions, duplicate_flags, strict=True)
        if is_duplicate
    ]

    issues: list[ValidationIssue] = []
    for code, label, positions in (
        (ValidationCode.NULL_RECORD_IDS, "null", null_positions),
        (ValidationCode.BLANK_RECORD_IDS, "blank", blank_positions),
        (ValidationCode.DUPLICATE_RECORD_IDS, "duplicate", duplicate_positions),
    ):
        if not positions:
            continue
        rows = _source_rows(loaded, positions)
        issues.append(
            ValidationIssue(
                code=code,
                severity=ValidationSeverity.ERROR,
                source_path=path,
                columns=(column,),
                affected_count=len(rows),
                sample_rows=_sample_rows(rows),
                message=(
                    f"Source '{path}' column '{column}' contains {len(rows)} {label} record "
                    f"identifier row(s); source rows: {_format_row_context(rows)}."
                ),
            )
        )
    return issues


def inspect_source(
    loaded: LoadedSource,
    required_columns: tuple[str, ...] = (),
) -> ValidationResult:
    """Collect every practical schema and identifier issue for one source."""
    path = loaded.source.path
    record_id = loaded.source.record_id
    expected_columns = tuple(dict.fromkeys((record_id, *required_columns)))
    actual_columns = tuple(loaded.data.columns)
    actual_column_set = set(actual_columns)
    issues: list[ValidationIssue] = []

    if loaded.data.empty:
        issues.append(
            ValidationIssue(
                code=ValidationCode.EMPTY_SOURCE,
                severity=ValidationSeverity.ERROR,
                source_path=path,
                affected_count=0,
                message=f"Source '{path}' contains no data rows.",
            )
        )

    missing_columns = tuple(
        column for column in expected_columns if column not in actual_column_set
    )
    if missing_columns:
        issues.append(
            ValidationIssue(
                code=ValidationCode.MISSING_REQUIRED_COLUMNS,
                severity=ValidationSeverity.ERROR,
                source_path=path,
                columns=missing_columns,
                affected_count=len(missing_columns),
                message=(
                    f"Source '{path}' is missing required column(s): "
                    f"{_format_columns(missing_columns)}."
                ),
            )
        )

    duplicate_columns = tuple(
        dict.fromkeys(
            str(column)
            for column, duplicated in zip(
                actual_columns,
                loaded.data.columns.duplicated(keep=False),
                strict=True,
            )
            if duplicated
        )
    )
    if duplicate_columns:
        issues.append(
            ValidationIssue(
                code=ValidationCode.DUPLICATE_COLUMNS,
                severity=ValidationSeverity.ERROR,
                source_path=path,
                columns=duplicate_columns,
                affected_count=len(duplicate_columns),
                message=(
                    f"Source '{path}' contains duplicate column name(s): "
                    f"{_format_columns(duplicate_columns)}."
                ),
            )
        )

    unexpected_columns = tuple(
        dict.fromkeys(str(column) for column in actual_columns if column not in expected_columns)
    )
    if unexpected_columns:
        issues.append(
            ValidationIssue(
                code=ValidationCode.UNEXPECTED_COLUMNS,
                severity=ValidationSeverity.WARNING,
                source_path=path,
                columns=unexpected_columns,
                affected_count=len(unexpected_columns),
                message=(
                    f"Source '{path}' contains unexpected column(s): "
                    f"{_format_columns(unexpected_columns)}; values are preserved but unused."
                ),
            )
        )

    record_id_is_unique_column = (
        record_id in actual_column_set and record_id not in duplicate_columns
    )
    if record_id_is_unique_column:
        issues.extend(_identifier_issues(loaded))

    return ValidationResult(loaded_source=loaded, issues=tuple(issues))


def inspect_sources(
    config: EngineConfig,
    left: LoadedSource,
    right: LoadedSource,
) -> tuple[ValidationResult, ValidationResult]:
    """Inspect both configured sources and retain every independent finding."""
    left_columns = tuple(mapping.left_column for mapping in config.field_mappings)
    right_columns = tuple(mapping.right_column for mapping in config.field_mappings)
    return (
        inspect_source(left, left_columns),
        inspect_source(right, right_columns),
    )


def validate_source(
    loaded: LoadedSource,
    required_columns: tuple[str, ...] = (),
) -> ValidatedSource:
    """Return a validated wrapper or raise one error containing all blocking findings."""
    result = inspect_source(loaded, required_columns)
    if not result.is_valid:
        raise SourceValidationError((result,))
    return ValidatedSource(loaded_source=loaded, warnings=result.warnings)


def validate_sources(
    config: EngineConfig,
    left: LoadedSource,
    right: LoadedSource,
) -> tuple[ValidatedSource, ValidatedSource]:
    """Validate both configured sources before they enter later pipeline stages."""
    results = inspect_sources(config, left, right)
    if any(not result.is_valid for result in results):
        raise SourceValidationError(results)
    return (
        ValidatedSource(
            loaded_source=results[0].loaded_source,
            warnings=results[0].warnings,
        ),
        ValidatedSource(
            loaded_source=results[1].loaded_source,
            warnings=results[1].warnings,
        ),
    )


__all__ = [
    "SourceValidationError",
    "ValidatedSource",
    "ValidationCode",
    "ValidationIssue",
    "ValidationResult",
    "ValidationSeverity",
    "inspect_source",
    "inspect_sources",
    "validate_source",
    "validate_sources",
]

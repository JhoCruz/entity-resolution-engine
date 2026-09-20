"""Create auditable comparison values without mutating validated source data."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, cast

import pandas as pd

from entity_resolution_engine.config import EngineConfig, SemanticFieldType
from entity_resolution_engine.validation import ValidatedSource

SOURCE_RECORD_ID_COLUMN = "source_record_id"
SOURCE_ROW_COLUMN = "source_row"


class NormalizationStep(StrEnum):
    """Stable names for each baseline transformation applied to a value."""

    COERCE_TO_TEXT = "coerce_to_text"
    UNICODE_NFKC = "unicode_nfkc"
    CASE_FOLD = "case_fold"
    PUNCTUATION_TO_SPACE = "punctuation_to_space"
    WHITESPACE_COLLAPSE = "whitespace_collapse"


@dataclass(frozen=True, slots=True)
class NormalizedValue:
    """One original value, its comparison form, and the transformations used."""

    original: object
    normalized: str | None
    transformations: tuple[NormalizationStep, ...] = ()


@dataclass(frozen=True, slots=True)
class NormalizedField:
    """Column metadata for one logical field in a normalized source table."""

    name: str
    source_column: str
    semantic_type: SemanticFieldType
    original_column: str
    normalized_column: str
    transformations_column: str


@dataclass(frozen=True, slots=True, eq=False)
class NormalizedSource:
    """A validated source plus a side-by-side, audit-friendly comparison table."""

    validated_source: ValidatedSource
    data: pd.DataFrame
    fields: tuple[NormalizedField, ...]

    @property
    def row_count(self) -> int:
        """Return the number of normalized source rows."""
        return len(self.data)


def _is_missing(value: object) -> bool:
    return bool(pd.isna(cast(Any, value)))


def _punctuation_to_space(value: str) -> str:
    return "".join(
        " " if unicodedata.category(character).startswith("P") else character for character in value
    )


def normalize_text(value: object) -> NormalizedValue:
    """Apply the transparent baseline text transformations in a stable order."""
    if not pd.api.types.is_scalar(value):
        raise TypeError("Normalization accepts scalar values only.")
    if _is_missing(value):
        return NormalizedValue(original=value, normalized=None)

    transformations: list[NormalizationStep] = []
    if isinstance(value, str):
        normalized = value
    else:
        normalized = str(value)
        transformations.append(NormalizationStep.COERCE_TO_TEXT)

    unicode_normalized = unicodedata.normalize("NFKC", normalized)
    if unicode_normalized != normalized:
        normalized = unicode_normalized
        transformations.append(NormalizationStep.UNICODE_NFKC)

    case_folded = normalized.casefold()
    if case_folded != normalized:
        normalized = case_folded
        transformations.append(NormalizationStep.CASE_FOLD)

    punctuation_normalized = _punctuation_to_space(normalized)
    if punctuation_normalized != normalized:
        normalized = punctuation_normalized
        transformations.append(NormalizationStep.PUNCTUATION_TO_SPACE)

    whitespace_normalized = " ".join(normalized.split())
    if whitespace_normalized != normalized:
        normalized = whitespace_normalized
        transformations.append(NormalizationStep.WHITESPACE_COLLAPSE)

    return NormalizedValue(
        original=value,
        normalized=normalized,
        transformations=tuple(transformations),
    )


def _field_metadata(
    name: str,
    source_column: str,
    semantic_type: SemanticFieldType,
) -> NormalizedField:
    return NormalizedField(
        name=name,
        source_column=source_column,
        semantic_type=semantic_type,
        original_column=f"{name}_original",
        normalized_column=f"{name}_normalized",
        transformations_column=f"{name}_transformations",
    )


def _normalize_source(
    source: ValidatedSource,
    fields: tuple[NormalizedField, ...],
) -> NormalizedSource:
    loaded = source.loaded_source
    normalized_data = pd.DataFrame(
        {
            SOURCE_RECORD_ID_COLUMN: pd.Series(
                loaded.data[loaded.source.record_id].tolist(),
                dtype=object,
            ),
            SOURCE_ROW_COLUMN: pd.Series(loaded.source_rows, dtype="int64"),
        }
    )

    for field in fields:
        results = tuple(
            normalize_text(value) for value in loaded.data[field.source_column].tolist()
        )
        normalized_data[field.original_column] = pd.Series(
            [result.original for result in results],
            dtype=object,
        )
        normalized_data[field.normalized_column] = pd.Series(
            [result.normalized for result in results],
            dtype=object,
        )
        normalized_data[field.transformations_column] = pd.Series(
            [tuple(step.value for step in result.transformations) for result in results],
            dtype=object,
        )

    return NormalizedSource(
        validated_source=source,
        data=normalized_data,
        fields=fields,
    )


def normalize_sources(
    config: EngineConfig,
    left: ValidatedSource,
    right: ValidatedSource,
) -> tuple[NormalizedSource, NormalizedSource]:
    """Normalize mapped fields from both validated sources without changing their data frames."""
    left_fields = tuple(
        _field_metadata(mapping.name, mapping.left_column, mapping.semantic_type)
        for mapping in config.field_mappings
    )
    right_fields = tuple(
        _field_metadata(mapping.name, mapping.right_column, mapping.semantic_type)
        for mapping in config.field_mappings
    )
    return (
        _normalize_source(left, left_fields),
        _normalize_source(right, right_fields),
    )


__all__ = [
    "SOURCE_RECORD_ID_COLUMN",
    "SOURCE_ROW_COLUMN",
    "NormalizationStep",
    "NormalizedField",
    "NormalizedSource",
    "NormalizedValue",
    "normalize_sources",
    "normalize_text",
]

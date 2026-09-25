"""Recover bounded candidate pairs from exact valid dates when name anchors fail."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from entity_resolution_engine.config import SemanticFieldType
from entity_resolution_engine.normalization import (
    SOURCE_ROW_COLUMN,
    NormalizedField,
    NormalizedSource,
)

MAX_PAIRS_PER_DATE_KEY = 1_000
MAX_DATE_CANDIDATES = 10_000


class DateBlockingLimitError(ValueError):
    """Raised when a common date would generate too many candidate pairs."""


class DateBlockStrategy(StrEnum):
    """A valid exact date can suggest a pair without proving identity."""

    EXACT_DATE = "exact_date"


@dataclass(frozen=True, slots=True)
class DateBlockOrigin:
    """Field and strategy, with no date value retained."""

    field: str
    strategy: DateBlockStrategy = DateBlockStrategy.EXACT_DATE


@dataclass(frozen=True, slots=True)
class DateCandidate:
    """Additional date-key candidate excluded from the exact and name stages."""

    left_source_row: int
    right_source_row: int
    origins: tuple[DateBlockOrigin, ...]


@dataclass(frozen=True, slots=True)
class DateBlockingResult:
    """Additional candidate pairs, with no decisions or source values."""

    candidates: tuple[DateCandidate, ...]


def _date_groups(source: NormalizedSource, field: NormalizedField) -> dict[str, list[int]]:
    groups: dict[str, list[int]] = defaultdict(list)
    for index in range(source.row_count):
        issue: object = source.data[field.issue_column].iat[index]
        value: object = source.data[field.normalized_column].iat[index]
        if issue is None and isinstance(value, str) and value:
            groups[value].append(index)
    return groups


def generate_date_candidates(
    left: NormalizedSource,
    right: NormalizedSource,
    *,
    excluded_source_rows: frozenset[tuple[int, int]] = frozenset(),
    excluded_left_rows: frozenset[int] = frozenset(),
    excluded_right_rows: frozenset[int] = frozenset(),
) -> DateBlockingResult:
    """Select additional valid equal dates, omitting existing pairs and accepted rows."""
    if tuple((f.name, f.semantic_type) for f in left.fields) != tuple(
        (f.name, f.semantic_type) for f in right.fields
    ):
        raise ValueError("Normalized field mappings do not match across sources.")

    left_rows = tuple(
        cast(int, left.data[SOURCE_ROW_COLUMN].iat[index]) for index in range(left.row_count)
    )
    right_rows = tuple(
        cast(int, right.data[SOURCE_ROW_COLUMN].iat[index]) for index in range(right.row_count)
    )
    candidates: dict[tuple[int, int], set[DateBlockOrigin]] = defaultdict(set)
    for left_field, right_field in zip(left.fields, right.fields, strict=True):
        if left_field.semantic_type is not SemanticFieldType.DATE:
            continue
        left_groups = _date_groups(left, left_field)
        right_groups = _date_groups(right, right_field)
        for key, left_indexes in left_groups.items():
            active_left = [
                index for index in left_indexes if left_rows[index] not in excluded_left_rows
            ]
            active_right = [
                index
                for index in right_groups.get(key, ())
                if right_rows[index] not in excluded_right_rows
            ]
            if len(active_left) * len(active_right) > MAX_PAIRS_PER_DATE_KEY:
                raise DateBlockingLimitError(
                    f"Date field '{left_field.name}' generates more than "
                    f"{MAX_PAIRS_PER_DATE_KEY} pairs from one value."
                )
            for left_index in active_left:
                for right_index in active_right:
                    pair = (left_rows[left_index], right_rows[right_index])
                    if (
                        pair in excluded_source_rows
                        or pair[0] in excluded_left_rows
                        or pair[1] in excluded_right_rows
                    ):
                        continue
                    candidates[left_index, right_index].add(DateBlockOrigin(left_field.name))
            if len(candidates) > MAX_DATE_CANDIDATES:
                raise DateBlockingLimitError(
                    f"Date blocking generates more than {MAX_DATE_CANDIDATES} new pairs."
                )

    return DateBlockingResult(
        candidates=tuple(
            DateCandidate(
                left_source_row=left_rows[left_index],
                right_source_row=right_rows[right_index],
                origins=tuple(
                    DateBlockOrigin(field.name)
                    for field in left.fields
                    if DateBlockOrigin(field.name) in candidates[left_index, right_index]
                ),
            )
            for left_index, right_index in sorted(candidates)
        ),
    )

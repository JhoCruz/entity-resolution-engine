"""Find bounded, value-free name candidates for later fuzzy scoring."""

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

MAX_PAIRS_PER_NAME_KEY = 1_000
MAX_NAME_CANDIDATE_PAIRS = 10_000


class NameBlockingLimitError(ValueError):
    """Raised when a common name key would create too many pairs."""


class NameBlockStrategy(StrEnum):
    """Two complementary, explainable anchors for a multi-token person name."""

    FIRST_LAST_INITIAL = "first_token_last_initial"
    LAST_FIRST_INITIAL = "last_token_first_initial"


@dataclass(frozen=True, slots=True)
class NameBlockOrigin:
    """Field and strategy responsible for finding a candidate, without its key."""

    field: str
    strategy: NameBlockStrategy


@dataclass(frozen=True, slots=True)
class NameCandidate:
    """One possible pair; source values and comparison keys are never stored."""

    left_source_row: int
    right_source_row: int
    origins: tuple[NameBlockOrigin, ...]


@dataclass(frozen=True, slots=True)
class NameBlockingResult:
    """Name candidates, still without scores or match decisions."""

    candidates: tuple[NameCandidate, ...]
    possible_pairs: int


def _name_key(
    source: NormalizedSource,
    field: NormalizedField,
    index: int,
    strategy: NameBlockStrategy,
) -> tuple[str, str] | None:
    value: object = source.data[field.normalized_column].iat[index]
    if not isinstance(value, str):
        return None
    tokens = value.split()
    if len(tokens) < 2 or any(
        len(token) < 2 or not token.isalpha() for token in (tokens[0], tokens[-1])
    ):
        return None

    first, last = tokens[0], tokens[-1]
    if strategy is NameBlockStrategy.FIRST_LAST_INITIAL:
        return first, last[0]
    return last, first[0]


def _groups(
    source: NormalizedSource,
    field: NormalizedField,
    strategy: NameBlockStrategy,
) -> dict[tuple[str, str], list[int]]:
    groups: dict[tuple[str, str], list[int]] = defaultdict(list)
    for index in range(source.row_count):
        key = _name_key(source, field, index, strategy)
        if key is not None:
            groups[key].append(index)
    return groups


def generate_name_candidates(
    left: NormalizedSource,
    right: NormalizedSource,
    *,
    excluded_source_rows: frozenset[tuple[int, int]] = frozenset(),
    excluded_left_rows: frozenset[int] = frozenset(),
    excluded_right_rows: frozenset[int] = frozenset(),
) -> NameBlockingResult:
    """Use two name anchors; skip exact pairs and rows already safely matched."""
    left_fields = tuple((field.name, field.semantic_type) for field in left.fields)
    right_fields = tuple((field.name, field.semantic_type) for field in right.fields)
    if left_fields != right_fields:
        raise ValueError("Normalized field mappings do not match across sources.")

    left_rows = tuple(
        cast(int, left.data[SOURCE_ROW_COLUMN].iat[index]) for index in range(left.row_count)
    )
    right_rows = tuple(
        cast(int, right.data[SOURCE_ROW_COLUMN].iat[index]) for index in range(right.row_count)
    )
    candidates: dict[tuple[int, int], set[NameBlockOrigin]] = defaultdict(set)
    for left_field, right_field in zip(left.fields, right.fields, strict=True):
        if left_field.semantic_type is not SemanticFieldType.PERSON_NAME:
            continue
        for strategy in NameBlockStrategy:
            left_groups = _groups(left, left_field, strategy)
            right_groups = _groups(right, right_field, strategy)
            for key, left_indexes in left_groups.items():
                right_indexes = right_groups.get(key, ())
                if len(left_indexes) * len(right_indexes) > MAX_PAIRS_PER_NAME_KEY:
                    raise NameBlockingLimitError(
                        f"Name field '{left_field.name}' with strategy '{strategy.value}' "
                        f"generates more than {MAX_PAIRS_PER_NAME_KEY} pairs from one key."
                    )
                for left_index in left_indexes:
                    for right_index in right_indexes:
                        if (
                            (left_rows[left_index], right_rows[right_index]) in excluded_source_rows
                            or left_rows[left_index] in excluded_left_rows
                            or right_rows[right_index] in excluded_right_rows
                        ):
                            continue
                        candidates[left_index, right_index].add(
                            NameBlockOrigin(left_field.name, strategy)
                        )
                if len(candidates) > MAX_NAME_CANDIDATE_PAIRS:
                    raise NameBlockingLimitError(
                        f"Name blocking generates more than {MAX_NAME_CANDIDATE_PAIRS} "
                        "new candidate pairs."
                    )

    return NameBlockingResult(
        candidates=tuple(
            NameCandidate(
                left_source_row=left_rows[left_index],
                right_source_row=right_rows[right_index],
                origins=tuple(
                    NameBlockOrigin(field.name, strategy)
                    for field in left.fields
                    for strategy in NameBlockStrategy
                    if NameBlockOrigin(field.name, strategy) in candidates[left_index, right_index]
                ),
            )
            for left_index, right_index in sorted(candidates)
        ),
        possible_pairs=left.row_count * right.row_count,
    )


__all__ = [
    "MAX_NAME_CANDIDATE_PAIRS",
    "MAX_PAIRS_PER_NAME_KEY",
    "NameBlockOrigin",
    "NameBlockStrategy",
    "NameBlockingLimitError",
    "NameBlockingResult",
    "NameCandidate",
    "generate_name_candidates",
]

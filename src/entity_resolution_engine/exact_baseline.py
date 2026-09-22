"""Build conservative exact-identifier decisions with inspectable evidence."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from entity_resolution_engine.config import EngineConfig, SemanticFieldType
from entity_resolution_engine.decision import MatchDecision
from entity_resolution_engine.normalization import (
    SOURCE_RECORD_ID_COLUMN,
    SOURCE_ROW_COLUMN,
    NormalizedField,
    NormalizedSource,
)

MAX_PAIRS_PER_IDENTIFIER_KEY = 1_000
MAX_CANDIDATE_PAIRS = 10_000


class CandidateLimitError(ValueError):
    """Raised before a repeated identifier creates an unbounded number of pairs."""


class EvidenceOutcome(StrEnum):
    """Exact evidence available for one mapped field in a candidate pair."""

    AGREE = "agree"
    CONFLICT = "conflict"
    MISSING = "missing"
    INVALID = "invalid"


class ExactReason(StrEnum):
    """Stable reasons for an exact baseline match or a review decision."""

    EXACT_IDENTIFIER = "exact_identifier"
    SUPPORTING_FIELD = "supporting_field"
    IDENTIFIER_COLLISION = "identifier_collision"
    ONE_TO_MANY = "one_to_many"
    MANY_TO_ONE = "many_to_one"
    FIELD_CONFLICT = "field_conflict"
    INVALID_FIELD = "invalid_field"
    NO_SUPPORTING_FIELD = "no_supporting_field"


@dataclass(frozen=True, slots=True)
class FieldEvidence:
    """Field-level equality score and safe reason, without source values."""

    name: str
    semantic_type: SemanticFieldType
    outcome: EvidenceOutcome
    score: float | None
    left_issue: str | None = None
    right_issue: str | None = None


@dataclass(frozen=True, slots=True, repr=False)
class ExactPair:
    """One candidate and its explainable decision; record IDs remain internal."""

    left_record_id: object
    right_record_id: object
    left_source_row: int
    right_source_row: int
    decision: MatchDecision
    matched_on: tuple[str, ...]
    evidence: tuple[FieldEvidence, ...]
    reasons: tuple[ExactReason, ...]


@dataclass(frozen=True, slots=True)
class ExactBaselineResult:
    """Pairs found by exact IDs and rows left for later candidate strategies."""

    pairs: tuple[ExactPair, ...]
    left_without_candidate: tuple[int, ...]
    right_without_candidate: tuple[int, ...]


def _key(source: NormalizedSource, field: NormalizedField, index: int) -> str | None:
    issue: object = source.data[field.issue_column].iat[index]
    value: object = source.data[field.normalized_column].iat[index]
    if issue is None and isinstance(value, str) and value:
        return value
    return None


def _field_evidence(
    left: NormalizedSource,
    right: NormalizedSource,
    left_field: NormalizedField,
    right_field: NormalizedField,
    left_index: int,
    right_index: int,
) -> FieldEvidence:
    left_issue: object = left.data[left_field.issue_column].iat[left_index]
    right_issue: object = right.data[right_field.issue_column].iat[right_index]
    safe_left_issue = left_issue if isinstance(left_issue, str) else None
    safe_right_issue = right_issue if isinstance(right_issue, str) else None
    if safe_left_issue or safe_right_issue:
        outcome = EvidenceOutcome.INVALID
        score = None
    else:
        left_key = _key(left, left_field, left_index)
        right_key = _key(right, right_field, right_index)
        if left_key is None or right_key is None:
            outcome = EvidenceOutcome.MISSING
            score = None
        elif left_key == right_key:
            outcome = EvidenceOutcome.AGREE
            score = 1.0
        else:
            outcome = EvidenceOutcome.CONFLICT
            score = 0.0

    return FieldEvidence(
        name=left_field.name,
        semantic_type=left_field.semantic_type,
        outcome=outcome,
        score=score,
        left_issue=safe_left_issue,
        right_issue=safe_right_issue,
    )


def _groups(source: NormalizedSource, field: NormalizedField) -> dict[str, list[int]]:
    grouped: dict[str, list[int]] = defaultdict(list)
    for index in range(source.row_count):
        key = _key(source, field, index)
        if key is not None:
            grouped[key].append(index)
    return grouped


def _candidate_pairs(
    left: NormalizedSource,
    right: NormalizedSource,
) -> tuple[dict[tuple[int, int], set[str]], set[tuple[int, int]]]:
    candidates: dict[tuple[int, int], set[str]] = defaultdict(set)
    collisions: set[tuple[int, int]] = set()
    for left_field, right_field in zip(left.fields, right.fields, strict=True):
        if left_field.semantic_type is not SemanticFieldType.IDENTIFIER:
            continue
        left_groups = _groups(left, left_field)
        right_groups = _groups(right, right_field)
        for key, left_indexes in left_groups.items():
            right_indexes = right_groups.get(key, ())
            if len(left_indexes) * len(right_indexes) > MAX_PAIRS_PER_IDENTIFIER_KEY:
                raise CandidateLimitError(
                    f"Identifier field '{left_field.name}' generates more than "
                    f"{MAX_PAIRS_PER_IDENTIFIER_KEY} pairs from one key; inspect duplicate values."
                )
            for left_index in left_indexes:
                for right_index in right_indexes:
                    pair = (left_index, right_index)
                    candidates[pair].add(left_field.name)
                    if len(left_indexes) > 1 or len(right_indexes) > 1:
                        collisions.add(pair)
            if len(candidates) > MAX_CANDIDATE_PAIRS:
                raise CandidateLimitError(
                    f"Exact identifiers generate more than {MAX_CANDIDATE_PAIRS} "
                    "candidate pairs; inspect input uniqueness."
                )
    return candidates, collisions


def _pair_decision(
    left: NormalizedSource,
    right: NormalizedSource,
    pair: tuple[int, int],
    matched_fields: set[str],
    collisions: set[tuple[int, int]],
    left_degrees: dict[int, int],
    right_degrees: dict[int, int],
) -> ExactPair:
    left_index, right_index = pair
    evidence = tuple(
        _field_evidence(left, right, left_field, right_field, left_index, right_index)
        for left_field, right_field in zip(left.fields, right.fields, strict=True)
    )
    supporting_field = any(
        item.outcome is EvidenceOutcome.AGREE
        and item.semantic_type is not SemanticFieldType.IDENTIFIER
        for item in evidence
    )

    reasons = [ExactReason.EXACT_IDENTIFIER]
    if pair in collisions:
        reasons.append(ExactReason.IDENTIFIER_COLLISION)
    if left_degrees[left_index] > 1:
        reasons.append(ExactReason.ONE_TO_MANY)
    if right_degrees[right_index] > 1:
        reasons.append(ExactReason.MANY_TO_ONE)
    if any(item.outcome is EvidenceOutcome.CONFLICT for item in evidence):
        reasons.append(ExactReason.FIELD_CONFLICT)
    if any(item.outcome is EvidenceOutcome.INVALID for item in evidence):
        reasons.append(ExactReason.INVALID_FIELD)
    if not supporting_field:
        reasons.append(ExactReason.NO_SUPPORTING_FIELD)

    decision = MatchDecision.MATCH if len(reasons) == 1 else MatchDecision.REVIEW
    if decision is MatchDecision.MATCH:
        reasons.append(ExactReason.SUPPORTING_FIELD)
    return ExactPair(
        left_record_id=left.data[SOURCE_RECORD_ID_COLUMN].iat[left_index],
        right_record_id=right.data[SOURCE_RECORD_ID_COLUMN].iat[right_index],
        left_source_row=cast(int, left.data[SOURCE_ROW_COLUMN].iat[left_index]),
        right_source_row=cast(int, right.data[SOURCE_ROW_COLUMN].iat[right_index]),
        decision=decision,
        matched_on=tuple(field.name for field in left.fields if field.name in matched_fields),
        evidence=evidence,
        reasons=tuple(reasons),
    )


def resolve_exact_identifiers(
    config: EngineConfig,
    left: NormalizedSource,
    right: NormalizedSource,
) -> ExactBaselineResult:
    """Decide exact-ID candidates without interpreting unmatched rows as non-matches."""
    for source, configured_source, side in (
        (left, config.left_source, "left"),
        (right, config.right_source, "right"),
    ):
        actual = tuple(
            (field.name, field.semantic_type, field.source_column) for field in source.fields
        )
        expected = tuple(
            (
                field.name,
                field.semantic_type,
                field.left_column if side == "left" else field.right_column,
            )
            for field in config.field_mappings
        )
        if actual != expected or source.validated_source.loaded_source.source != configured_source:
            raise ValueError("Normalized field mappings do not match the job configuration.")

    candidates, collisions = _candidate_pairs(left, right)
    left_partners: dict[int, set[int]] = defaultdict(set)
    right_partners: dict[int, set[int]] = defaultdict(set)
    for left_index, right_index in candidates:
        left_partners[left_index].add(right_index)
        right_partners[right_index].add(left_index)
    left_degrees = {index: len(partners) for index, partners in left_partners.items()}
    right_degrees = {index: len(partners) for index, partners in right_partners.items()}

    pairs = tuple(
        _pair_decision(
            left,
            right,
            pair,
            candidates[pair],
            collisions,
            left_degrees,
            right_degrees,
        )
        for pair in sorted(candidates)
    )
    return ExactBaselineResult(
        pairs=pairs,
        left_without_candidate=tuple(
            cast(int, left.data[SOURCE_ROW_COLUMN].iat[index])
            for index in range(left.row_count)
            if index not in left_partners
        ),
        right_without_candidate=tuple(
            cast(int, right.data[SOURCE_ROW_COLUMN].iat[index])
            for index in range(right.row_count)
            if index not in right_partners
        ),
    )


__all__ = [
    "MAX_CANDIDATE_PAIRS",
    "MAX_PAIRS_PER_IDENTIFIER_KEY",
    "CandidateLimitError",
    "EvidenceOutcome",
    "ExactBaselineResult",
    "ExactPair",
    "ExactReason",
    "FieldEvidence",
    "resolve_exact_identifiers",
]

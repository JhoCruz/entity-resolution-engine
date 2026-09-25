"""Score bounded candidates transparently, without treating similarity as probability."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from rapidfuzz.fuzz import ratio

from entity_resolution_engine.blocking import NameCandidate
from entity_resolution_engine.config import EngineConfig, SemanticFieldType
from entity_resolution_engine.date_blocking import DateCandidate
from entity_resolution_engine.decision import MatchDecision
from entity_resolution_engine.exact_baseline import EvidenceOutcome, FieldEvidence
from entity_resolution_engine.normalization import (
    SOURCE_RECORD_ID_COLUMN,
    SOURCE_ROW_COLUMN,
    NormalizedField,
    NormalizedSource,
)


class FuzzyReason(StrEnum):
    """Reasons an approximate or date-only candidate is held for review."""

    UNCALIBRATED_SCORE = "uncalibrated_score"
    IDENTIFIER_CONFLICT = "identifier_conflict"
    STRUCTURED_CONFLICT = "structured_conflict"
    INVALID_FIELD = "invalid_field"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    DATE_ONLY_CANDIDATE = "date_only_candidate"
    CALIBRATED_MATCH = "calibrated_match"
    CALIBRATED_REVIEW = "calibrated_review"
    BELOW_REVIEW_THRESHOLD = "below_review_threshold"


@dataclass(frozen=True, slots=True)
class WeightedEvidence:
    """A value-free field score with its configured weight."""

    field: FieldEvidence
    weight: float


@dataclass(frozen=True, slots=True, repr=False)
class ScoredPair:
    """One approximate candidate; original record identifiers stay out of repr."""

    left_record_id: object
    right_record_id: object
    left_source_row: int
    right_source_row: int
    decision: MatchDecision
    stage: str
    score: float | None
    evidence: tuple[WeightedEvidence, ...]
    reasons: tuple[FuzzyReason, ...]
    origins: tuple[str, ...]


def _score_field(
    left: NormalizedSource,
    right: NormalizedSource,
    left_field: NormalizedField,
    right_field: NormalizedField,
    left_index: int,
    right_index: int,
) -> FieldEvidence:
    left_issue: object = left.data[left_field.issue_column].iat[left_index]
    right_issue: object = right.data[right_field.issue_column].iat[right_index]
    if left_issue is not None or right_issue is not None:
        return FieldEvidence(
            left_field.name,
            left_field.semantic_type,
            EvidenceOutcome.INVALID,
            None,
            left_issue if isinstance(left_issue, str) else None,
            right_issue if isinstance(right_issue, str) else None,
        )

    left_key: object = left.data[left_field.normalized_column].iat[left_index]
    right_key: object = right.data[right_field.normalized_column].iat[right_index]
    if (
        not isinstance(left_key, str)
        or not left_key
        or not isinstance(right_key, str)
        or not right_key
    ):
        return FieldEvidence(
            left_field.name, left_field.semantic_type, EvidenceOutcome.MISSING, None
        )

    if left_key == right_key:
        similarity = 1.0
    elif left_field.semantic_type in {SemanticFieldType.PERSON_NAME, SemanticFieldType.TEXT}:
        similarity = ratio(left_key, right_key) / 100.0
    else:
        # A nearly equal identifier, date, phone or e-mail is not evidence of identity.
        similarity = 0.0

    return FieldEvidence(
        left_field.name,
        left_field.semantic_type,
        EvidenceOutcome.AGREE if similarity == 1.0 else EvidenceOutcome.CONFLICT,
        similarity,
    )


def score_candidates(
    config: EngineConfig,
    left: NormalizedSource,
    right: NormalizedSource,
    candidates: tuple[NameCandidate | DateCandidate, ...],
) -> tuple[ScoredPair, ...]:
    """Weight candidate fields, but abstain until thresholds are validated on labels.

    Missing and invalid fields do not contribute to the denominator. An exact
    structured-field conflict contributes zero, never approximate similarity.
    Scores are similarity values, not calibrated probabilities of a match.
    """
    left_positions = {
        cast(int, row): index for index, row in enumerate(left.data[SOURCE_ROW_COLUMN].tolist())
    }
    right_positions = {
        cast(int, row): index for index, row in enumerate(right.data[SOURCE_ROW_COLUMN].tolist())
    }
    result: list[ScoredPair] = []
    for candidate in candidates:
        left_index = left_positions[candidate.left_source_row]
        right_index = right_positions[candidate.right_source_row]
        evidence = tuple(
            WeightedEvidence(
                field=_score_field(left, right, left_field, right_field, left_index, right_index),
                weight=mapping.weight,
            )
            for mapping, left_field, right_field in zip(
                config.field_mappings, left.fields, right.fields, strict=True
            )
        )
        comparable = tuple(item for item in evidence if item.field.score is not None)
        total_weight = sum(item.weight for item in comparable)
        score = (
            sum(item.weight * cast(float, item.field.score) for item in comparable) / total_weight
            if total_weight
            else None
        )
        reasons = [FuzzyReason.UNCALIBRATED_SCORE]
        if isinstance(candidate, DateCandidate):
            reasons.append(FuzzyReason.DATE_ONLY_CANDIDATE)
        if any(
            item.field.semantic_type is SemanticFieldType.IDENTIFIER
            and item.field.outcome is EvidenceOutcome.CONFLICT
            for item in evidence
        ):
            reasons.append(FuzzyReason.IDENTIFIER_CONFLICT)
        if any(
            item.field.semantic_type
            in {SemanticFieldType.DATE, SemanticFieldType.EMAIL, SemanticFieldType.PHONE}
            and item.field.outcome is EvidenceOutcome.CONFLICT
            for item in evidence
        ):
            reasons.append(FuzzyReason.STRUCTURED_CONFLICT)
        if any(item.field.outcome is EvidenceOutcome.INVALID for item in evidence):
            reasons.append(FuzzyReason.INVALID_FIELD)
        if not any(
            item.field.semantic_type is not SemanticFieldType.PERSON_NAME
            and item.field.outcome is EvidenceOutcome.AGREE
            for item in evidence
        ):
            reasons.append(FuzzyReason.INSUFFICIENT_EVIDENCE)
        result.append(
            ScoredPair(
                left_record_id=left.data[SOURCE_RECORD_ID_COLUMN].iat[left_index],
                right_record_id=right.data[SOURCE_RECORD_ID_COLUMN].iat[right_index],
                left_source_row=candidate.left_source_row,
                right_source_row=candidate.right_source_row,
                decision=MatchDecision.REVIEW,
                stage="date_blocking"
                if isinstance(candidate, DateCandidate)
                else "name_similarity",
                score=score,
                evidence=evidence,
                reasons=tuple(reasons),
                origins=tuple(
                    f"{origin.field}:{origin.strategy.value}" for origin in candidate.origins
                ),
            )
        )
    return tuple(result)

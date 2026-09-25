"""Conservative, explicitly opted-in policy tuned only on synthetic labels."""

from __future__ import annotations

import json
import math
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path
from typing import cast

from entity_resolution_engine.config import EngineConfig
from entity_resolution_engine.decision import DecisionPolicy, MatchDecision
from entity_resolution_engine.exact_baseline import EvidenceOutcome, ExactPair
from entity_resolution_engine.scoring import FuzzyReason, ScoredPair


class PolicyError(ValueError):
    """Raised for a malformed or incompatible opt-in calibration file."""


@dataclass(frozen=True, slots=True)
class SyntheticPolicy:
    """Thresholds backed by one labeled synthetic tuning split, not real-world certification."""

    automatic_match: float
    review: float
    automatic_enabled: bool
    field_contract: tuple[tuple[str, str, float], ...]
    source: str = "synthetic_tuning_only"

    def __post_init__(self) -> None:
        DecisionPolicy(self.automatic_match, self.review)
        if self.source != "synthetic_tuning_only":
            raise PolicyError("Unsupported calibration source.")


def field_contract(config: EngineConfig) -> tuple[tuple[str, str, float], ...]:
    """Capture mapping semantics and weights so a policy cannot silently change meaning."""
    return tuple(
        (field.name, field.semantic_type.value, field.weight) for field in config.field_mappings
    )


def _eligible(
    pair: ScoredPair,
    left_degrees: Counter[int],
    right_degrees: Counter[int],
) -> bool:
    """Require one-to-one name evidence with an independent exact supporting field."""
    risky = {
        FuzzyReason.IDENTIFIER_CONFLICT,
        FuzzyReason.STRUCTURED_CONFLICT,
        FuzzyReason.INVALID_FIELD,
        FuzzyReason.INSUFFICIENT_EVIDENCE,
        FuzzyReason.DATE_ONLY_CANDIDATE,
    }
    return (
        pair.stage == "name_similarity"
        and pair.score is not None
        and left_degrees[pair.left_source_row] == 1
        and right_degrees[pair.right_source_row] == 1
        and not risky.intersection(pair.reasons)
        and any(
            item.field.semantic_type.value not in {"person_name", "text"}
            and item.field.outcome is EvidenceOutcome.AGREE
            for item in pair.evidence
        )
    )


def candidate_degrees(
    exact: tuple[ExactPair, ...], scored: tuple[ScoredPair, ...]
) -> tuple[Counter[int], Counter[int]]:
    """Include competing exact reviews when evaluating one-to-one fuzzy evidence."""
    left = Counter(pair.left_source_row for pair in exact if pair.decision is MatchDecision.REVIEW)
    right = Counter(
        pair.right_source_row for pair in exact if pair.decision is MatchDecision.REVIEW
    )
    left.update(pair.left_source_row for pair in scored)
    right.update(pair.right_source_row for pair in scored)
    return left, right


def apply_policy(
    exact: tuple[ExactPair, ...],
    scored: tuple[ScoredPair, ...],
    policy: SyntheticPolicy,
) -> tuple[ScoredPair, ...]:
    """Resolve only independently corroborated, unique fuzzy pairs; preserve abstention."""
    left_degrees, right_degrees = candidate_degrees(exact, scored)
    decided: list[ScoredPair] = []
    for pair in scored:
        reasons = [
            reason for reason in pair.reasons if reason is not FuzzyReason.UNCALIBRATED_SCORE
        ]
        if (
            policy.automatic_enabled
            and pair.score is not None
            and pair.score >= policy.automatic_match
            and _eligible(pair, left_degrees, right_degrees)
        ):
            decision = MatchDecision.MATCH
            reasons.append(FuzzyReason.CALIBRATED_MATCH)
        elif (
            pair.score is not None
            and pair.score < policy.review
            and pair.stage == "name_similarity"
            and FuzzyReason.INVALID_FIELD not in pair.reasons
            and FuzzyReason.IDENTIFIER_CONFLICT not in pair.reasons
            and FuzzyReason.STRUCTURED_CONFLICT not in pair.reasons
        ):
            decision = MatchDecision.NO_MATCH
            reasons.append(FuzzyReason.BELOW_REVIEW_THRESHOLD)
        else:
            decision = MatchDecision.REVIEW
            reasons.append(FuzzyReason.CALIBRATED_REVIEW)
        decided.append(replace(pair, decision=decision, reasons=tuple(reasons)))
    return tuple(decided)


def load_policy(path: Path, config: EngineConfig) -> SyntheticPolicy:
    """Read a synthetic-only policy with strict field and numeric compatibility checks."""
    try:
        data: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise PolicyError("Cannot read a valid calibration JSON file.") from error
    if not isinstance(data, dict):
        raise PolicyError("Calibration must be a JSON object.")
    root = cast(dict[str, object], data)
    if root.get("schema_version") != 1 or root.get("source") != "synthetic_tuning_only":
        raise PolicyError("Unsupported calibration schema or source.")
    if not isinstance(root.get("field_contract"), list):
        raise PolicyError("Calibration field contract is missing.")
    expected = [list(item) for item in field_contract(config)]
    if root["field_contract"] != expected:
        raise PolicyError("Calibration field names, types, or weights differ from this job.")
    thresholds: object = root.get("thresholds")
    if not isinstance(thresholds, dict):
        raise PolicyError("Calibration thresholds are missing.")
    values = cast(dict[str, object], thresholds)
    review = values.get("review")
    automatic = values.get("automatic_match")
    enabled = values.get("automatic_enabled")
    if (
        isinstance(review, bool)
        or not isinstance(review, (int, float))
        or isinstance(automatic, bool)
        or not isinstance(automatic, (int, float))
        or not isinstance(enabled, bool)
        or not math.isfinite(review)
        or not math.isfinite(automatic)
    ):
        raise PolicyError("Calibration thresholds must be finite numbers and a boolean flag.")
    try:
        return SyntheticPolicy(float(automatic), float(review), enabled, field_contract(config))
    except ValueError as error:
        raise PolicyError("Calibration threshold ordering is invalid.") from error

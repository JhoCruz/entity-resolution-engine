"""Choose a cautious demo policy using only labeled synthetic tuning records."""

from __future__ import annotations

import math

from entity_resolution_engine.config import EngineConfig
from entity_resolution_engine.policy import (
    SyntheticPolicy,
    _eligible,
    candidate_degrees,
    field_contract,
)
from entity_resolution_engine.reconciliation import ReconciliationResult

_MATCH_THRESHOLDS = (0.90, 0.92, 0.94, 0.96, 0.98, 1.0)


def calibrate(
    config: EngineConfig,
    result: ReconciliationResult,
    truth: set[tuple[str, str]],
) -> SyntheticPolicy:
    """Keep all observed true candidates reviewable and forbid tuning-set false matches.

    This is a synthetic demonstration, not evidence of safety on unseen real data.
    The final benchmark split must not be used to choose thresholds.
    """
    left_degrees, right_degrees = candidate_degrees(result.exact.pairs, result.scored)
    candidates = tuple(
        pair for pair in result.scored if _eligible(pair, left_degrees, right_degrees)
    )
    chosen = 1.0
    automatic_enabled = False
    for threshold in _MATCH_THRESHOLDS:
        accepted = tuple(
            pair for pair in candidates if pair.score is not None and pair.score >= threshold
        )
        if not accepted:
            continue
        if any(
            (str(pair.left_record_id), str(pair.right_record_id)) not in truth for pair in accepted
        ):
            continue
        chosen = threshold
        automatic_enabled = True
        break

    true_scores = tuple(
        pair.score
        for pair in result.scored
        if (str(pair.left_record_id), str(pair.right_record_id)) in truth and pair.score is not None
    )
    review = math.floor(min(true_scores) * 100) / 100 if true_scores else 0.0
    review = min(review, chosen - 0.01)
    return SyntheticPolicy(chosen, review, automatic_enabled, field_contract(config))

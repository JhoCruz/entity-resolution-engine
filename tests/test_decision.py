"""Tests for confidence-based match decisions."""

import pytest

from entity_resolution_engine.decision import DecisionPolicy, MatchDecision


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (0.0, MatchDecision.NO_MATCH),
        (0.69, MatchDecision.NO_MATCH),
        (0.70, MatchDecision.REVIEW),
        (0.89, MatchDecision.REVIEW),
        (0.90, MatchDecision.MATCH),
        (1.0, MatchDecision.MATCH),
    ],
)
def test_default_policy_boundaries(score: float, expected: MatchDecision) -> None:
    assert DecisionPolicy().classify(score) is expected


@pytest.mark.parametrize(
    ("automatic_match_threshold", "review_threshold"),
    [
        (0.90, -0.01),
        (0.90, 0.90),
        (0.80, 0.90),
        (1.01, 0.70),
    ],
)
def test_policy_rejects_invalid_thresholds(
    automatic_match_threshold: float,
    review_threshold: float,
) -> None:
    with pytest.raises(ValueError, match="Thresholds must satisfy"):
        DecisionPolicy(
            automatic_match_threshold=automatic_match_threshold,
            review_threshold=review_threshold,
        )


@pytest.mark.parametrize("score", [-0.01, 1.01])
def test_policy_rejects_invalid_scores(score: float) -> None:
    with pytest.raises(ValueError, match="Score must be between 0 and 1"):
        DecisionPolicy().classify(score)

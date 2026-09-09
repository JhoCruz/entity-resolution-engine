"""Confidence-based match decisions with an explicit review region."""

from dataclasses import dataclass
from enum import StrEnum


class MatchDecision(StrEnum):
    """Possible outcomes for a candidate record pair."""

    MATCH = "match"
    REVIEW = "review"
    NO_MATCH = "no_match"


@dataclass(frozen=True, slots=True)
class DecisionPolicy:
    """Convert a normalized confidence score into an auditable decision.

    Scores below ``review_threshold`` are rejected. Scores in the review region
    are deliberately left unresolved instead of being forced into a binary answer.
    """

    automatic_match_threshold: float = 0.90
    review_threshold: float = 0.70

    def __post_init__(self) -> None:
        if not 0.0 <= self.review_threshold < self.automatic_match_threshold <= 1.0:
            message = (
                "Thresholds must satisfy 0 <= review_threshold < automatic_match_threshold <= 1."
            )
            raise ValueError(message)

    def classify(self, score: float) -> MatchDecision:
        """Classify one confidence score, preserving uncertainty as review."""
        if not 0.0 <= score <= 1.0:
            raise ValueError("Score must be between 0 and 1.")
        if score >= self.automatic_match_threshold:
            return MatchDecision.MATCH
        if score >= self.review_threshold:
            return MatchDecision.REVIEW
        return MatchDecision.NO_MATCH

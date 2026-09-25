"""Evaluate selected and automatic pairs against separately stored ground truth."""

from __future__ import annotations

from dataclasses import dataclass

from entity_resolution_engine.decision import MatchDecision
from entity_resolution_engine.exact_baseline import ExactPair
from entity_resolution_engine.reconciliation import ReconciliationResult
from entity_resolution_engine.scoring import ScoredPair


@dataclass(frozen=True, slots=True)
class EvaluationMetrics:
    """Counts and rates with explicit denominators, including missed blocking pairs."""

    true_pairs: int
    selected_pairs: int
    selected_true_pairs: int
    automatic_matches: int
    true_positives: int
    false_positives: int
    false_negatives: int
    reviews: int
    reviewed_true_pairs: int
    precision: float
    recall: float
    f1: float
    review_rate: float
    blocking_recall: float
    false_match_examples: tuple[dict[str, str], ...]


def evaluate(
    result: ReconciliationResult,
    truth: set[tuple[str, str]],
) -> EvaluationMetrics:
    """Count automatic matches as predictions; a review is not a correct match yet.

    For synthetic benchmarks only: false-match examples contain source record IDs.
    Do not publish this result for real data without removing those identifiers.
    """
    pairs: tuple[ExactPair | ScoredPair, ...] = (*result.exact.pairs, *result.scored)
    selected = {(str(pair.left_record_id), str(pair.right_record_id)) for pair in pairs}
    accepted = {
        (str(pair.left_record_id), str(pair.right_record_id))
        for pair in pairs
        if pair.decision is MatchDecision.MATCH
    }
    reviewed = {
        (str(pair.left_record_id), str(pair.right_record_id))
        for pair in pairs
        if pair.decision is MatchDecision.REVIEW
    }
    true_positives = len(accepted & truth)
    false_positives = len(accepted - truth)
    false_negatives = len(truth - accepted)
    precision = true_positives / len(accepted) if accepted else 0.0
    recall = true_positives / len(truth) if truth else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    false_examples = tuple(
        {
            "left_record_id": left_id,
            "right_record_id": right_id,
        }
        for left_id, right_id in sorted(accepted - truth)[:5]
    )
    return EvaluationMetrics(
        true_pairs=len(truth),
        selected_pairs=len(selected),
        selected_true_pairs=len(selected & truth),
        automatic_matches=len(accepted),
        true_positives=true_positives,
        false_positives=false_positives,
        false_negatives=false_negatives,
        reviews=len(reviewed),
        reviewed_true_pairs=len(reviewed & truth),
        precision=precision,
        recall=recall,
        f1=f1,
        review_rate=len(reviewed) / len(selected) if selected else 0.0,
        blocking_recall=len(selected & truth) / len(truth) if truth else 0.0,
        false_match_examples=false_examples,
    )

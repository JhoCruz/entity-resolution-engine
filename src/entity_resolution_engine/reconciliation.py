"""Compose validated exact, name, and date candidate stages into one job."""

from __future__ import annotations

from dataclasses import dataclass

from entity_resolution_engine.blocking import NameBlockingResult, generate_name_candidates
from entity_resolution_engine.config import EngineConfig
from entity_resolution_engine.date_blocking import DateBlockingResult, generate_date_candidates
from entity_resolution_engine.decision import MatchDecision
from entity_resolution_engine.exact_baseline import ExactBaselineResult, resolve_exact_identifiers
from entity_resolution_engine.ingestion import load_sources
from entity_resolution_engine.normalization import NormalizedSource, normalize_sources
from entity_resolution_engine.scoring import ScoredPair, score_candidates
from entity_resolution_engine.validation import validate_sources


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    """Full in-memory job result, including private source values for opt-in audit."""

    left: NormalizedSource
    right: NormalizedSource
    exact: ExactBaselineResult
    names: NameBlockingResult
    dates: DateBlockingResult
    scored: tuple[ScoredPair, ...]


def reconcile(config: EngineConfig) -> ReconciliationResult:
    """Load, validate, normalize, find candidates, and abstain on fuzzy pairs."""
    loaded_left, loaded_right = load_sources(config)
    validated_left, validated_right = validate_sources(config, loaded_left, loaded_right)
    left, right = normalize_sources(config, validated_left, validated_right)
    exact = resolve_exact_identifiers(config, left, right)
    matches = tuple(pair for pair in exact.pairs if pair.decision is MatchDecision.MATCH)
    names = generate_name_candidates(
        left,
        right,
        excluded_source_rows=frozenset(
            (pair.left_source_row, pair.right_source_row) for pair in exact.pairs
        ),
        excluded_left_rows=frozenset(pair.left_source_row for pair in matches),
        excluded_right_rows=frozenset(pair.right_source_row for pair in matches),
    )
    dates = generate_date_candidates(
        left,
        right,
        excluded_source_rows=frozenset(
            (pair.left_source_row, pair.right_source_row) for pair in exact.pairs
        )
        | frozenset((pair.left_source_row, pair.right_source_row) for pair in names.candidates),
        excluded_left_rows=frozenset(pair.left_source_row for pair in matches),
        excluded_right_rows=frozenset(pair.right_source_row for pair in matches),
    )
    scored = score_candidates(config, left, right, (*names.candidates, *dates.candidates))
    return ReconciliationResult(left, right, exact, names, dates, scored)

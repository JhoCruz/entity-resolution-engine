"""Behavioral tests for the conservative exact-identifier baseline."""

from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

from entity_resolution_engine import exact_baseline
from entity_resolution_engine.config import (
    EngineConfig,
    FieldMapping,
    FileType,
    SemanticFieldType,
    SourceConfig,
    load_config,
)
from entity_resolution_engine.decision import DecisionPolicy, MatchDecision
from entity_resolution_engine.exact_baseline import (
    CandidateLimitError,
    EvidenceOutcome,
    ExactBaselineResult,
    ExactReason,
    resolve_exact_identifiers,
)
from entity_resolution_engine.ingestion import LoadedSource, load_sources
from entity_resolution_engine.normalization import normalize_sources
from entity_resolution_engine.validation import validate_sources

ID = ("identity", SemanticFieldType.IDENTIFIER)
NAME = ("name", SemanticFieldType.PERSON_NAME)
DATE = ("birthday", SemanticFieldType.DATE)


def _resolve(
    tmp_path: Path,
    left_rows: Sequence[Mapping[str, object]],
    right_rows: Sequence[Mapping[str, object]],
    fields: tuple[tuple[str, SemanticFieldType], ...] = (ID, NAME),
) -> ExactBaselineResult:
    config = EngineConfig(
        left_source=SourceConfig(tmp_path / "left.csv", FileType.CSV, "left_row_id"),
        right_source=SourceConfig(tmp_path / "right.csv", FileType.CSV, "right_row_id"),
        field_mappings=tuple(
            FieldMapping(name, name, name, field_type) for name, field_type in fields
        ),
        decision_policy=DecisionPolicy(),
    )
    left_data, right_data = pd.DataFrame(left_rows), pd.DataFrame(right_rows)
    loaded_left = LoadedSource(config.left_source, left_data, tuple(range(2, len(left_rows) + 2)))
    loaded_right = LoadedSource(
        config.right_source, right_data, tuple(range(2, len(right_rows) + 2))
    )
    valid_left, valid_right = validate_sources(config, loaded_left, loaded_right)
    normalized_left, normalized_right = normalize_sources(config, valid_left, valid_right)
    result = resolve_exact_identifiers(config, normalized_left, normalized_right)
    pd.testing.assert_frame_equal(left_data, pd.DataFrame(left_rows))
    pd.testing.assert_frame_equal(right_data, pd.DataFrame(right_rows))
    return result


def test_example_csv_xlsx_resolves_four_exact_pairs_with_component_scores() -> None:
    config = load_config("examples/basic-job.toml")
    loaded_left, loaded_right = load_sources(config)
    validated_left, validated_right = validate_sources(config, loaded_left, loaded_right)
    normalized_left, normalized_right = normalize_sources(config, validated_left, validated_right)

    result = resolve_exact_identifiers(config, normalized_left, normalized_right)

    assert len(result.pairs) == 4
    assert all(pair.decision is MatchDecision.MATCH for pair in result.pairs)
    assert [(pair.left_source_row, pair.right_source_row) for pair in result.pairs] == [
        (2, 2),
        (3, 3),
        (4, 4),
        (5, 5),
    ]
    assert result.pairs[0].left_record_id == "A-001"
    assert result.pairs[0].right_record_id == "B-001"
    assert result.pairs[0].matched_on == ("tax_id",)
    assert [field.score for field in result.pairs[0].evidence] == [1.0, 1.0, 1.0]
    assert result.pairs[0].reasons == (
        ExactReason.EXACT_IDENTIFIER,
        ExactReason.SUPPORTING_FIELD,
    )
    assert result.left_without_candidate == result.right_without_candidate == ()


def test_duplicate_normalized_identifier_requires_review(tmp_path: Path) -> None:
    result = _resolve(
        tmp_path,
        [
            {"left_row_id": "L-1", "identity": "SYN-001", "name": "Synthetic Alpha"},
            {"left_row_id": "L-2", "identity": "SYN001", "name": "Synthetic Alpha"},
        ],
        [{"right_row_id": "R-1", "identity": "SYN001", "name": "Synthetic Alpha"}],
    )

    assert len(result.pairs) == 2
    assert all(pair.decision is MatchDecision.REVIEW for pair in result.pairs)
    assert all(ExactReason.IDENTIFIER_COLLISION in pair.reasons for pair in result.pairs)
    assert all(ExactReason.MANY_TO_ONE in pair.reasons for pair in result.pairs)
    assert result.left_without_candidate == result.right_without_candidate == ()


def test_different_identifier_fields_create_one_to_many_review(tmp_path: Path) -> None:
    result = _resolve(
        tmp_path,
        [
            {
                "left_row_id": "L-1",
                "identity": "SYN-A",
                "secondary": "SYN-B",
                "name": "Synthetic Alpha",
            }
        ],
        [
            {
                "right_row_id": "R-1",
                "identity": "SYN-A",
                "secondary": "SYN-C",
                "name": "Synthetic Alpha",
            },
            {
                "right_row_id": "R-2",
                "identity": "SYN-D",
                "secondary": "SYN-B",
                "name": "Synthetic Alpha",
            },
        ],
        (ID, ("secondary", SemanticFieldType.IDENTIFIER), NAME),
    )

    assert len(result.pairs) == 2
    assert [pair.matched_on for pair in result.pairs] == [("identity",), ("secondary",)]
    assert all(pair.decision is MatchDecision.REVIEW for pair in result.pairs)
    assert all(ExactReason.ONE_TO_MANY in pair.reasons for pair in result.pairs)
    assert all(ExactReason.FIELD_CONFLICT in pair.reasons for pair in result.pairs)
    assert result.pairs[0].evidence[1].score == 0.0


def test_two_identifiers_produce_one_pair_with_both_origins(tmp_path: Path) -> None:
    result = _resolve(
        tmp_path,
        [
            {
                "left_row_id": "L-1",
                "identity": "SYN-A",
                "secondary": "SYN-B",
                "name": "Synthetic Alpha",
            }
        ],
        [
            {
                "right_row_id": "R-1",
                "identity": "SYN-A",
                "secondary": "SYN-B",
                "name": "Synthetic Alpha",
            }
        ],
        (ID, ("secondary", SemanticFieldType.IDENTIFIER), NAME),
    )

    assert len(result.pairs) == 1
    assert result.pairs[0].matched_on == ("identity", "secondary")
    assert result.pairs[0].decision is MatchDecision.MATCH


def test_conflicting_date_sends_corroborated_pair_to_review(tmp_path: Path) -> None:
    result = _resolve(
        tmp_path,
        [
            {
                "left_row_id": "L-1",
                "identity": "SYN-1",
                "name": "Synthetic Alpha",
                "birthday": "2000-01-01",
            }
        ],
        [
            {
                "right_row_id": "R-1",
                "identity": "SYN1",
                "name": "Synthetic Alpha",
                "birthday": "2000-01-02",
            }
        ],
        (ID, NAME, DATE),
    )

    pair = result.pairs[0]
    assert pair.decision is MatchDecision.REVIEW
    assert ExactReason.FIELD_CONFLICT in pair.reasons
    assert pair.evidence[2].outcome is EvidenceOutcome.CONFLICT
    assert pair.evidence[2].score == 0.0


def test_invalid_date_is_evidence_for_review_without_exposing_value(tmp_path: Path) -> None:
    result = _resolve(
        tmp_path,
        [
            {
                "left_row_id": "L-1",
                "identity": "SYN-1",
                "name": "Synthetic Alpha",
                "birthday": "03/04/2024",
            }
        ],
        [
            {
                "right_row_id": "R-1",
                "identity": "SYN1",
                "name": "Synthetic Alpha",
                "birthday": "2024-04-03",
            }
        ],
        (ID, NAME, DATE),
    )

    pair = result.pairs[0]
    assert pair.decision is MatchDecision.REVIEW
    assert ExactReason.INVALID_FIELD in pair.reasons
    assert pair.evidence[2].outcome is EvidenceOutcome.INVALID
    assert pair.evidence[2].score is None
    assert pair.evidence[2].left_issue == "ambiguous_date"
    assert pair.evidence[2].right_issue is None
    assert "03/04/2024" not in repr(pair)


def test_identifier_alone_does_not_establish_match(tmp_path: Path) -> None:
    result = _resolve(
        tmp_path,
        [{"left_row_id": "L-1", "identity": "SYN-1", "name": ""}],
        [{"right_row_id": "R-1", "identity": "SYN1", "name": ""}],
    )

    pair = result.pairs[0]
    assert pair.decision is MatchDecision.REVIEW
    assert ExactReason.NO_SUPPORTING_FIELD in pair.reasons
    assert pair.evidence[1].outcome is EvidenceOutcome.MISSING
    assert pair.evidence[1].score is None


def test_empty_identifiers_produce_no_candidates_and_no_final_non_match(tmp_path: Path) -> None:
    result = _resolve(
        tmp_path,
        [{"left_row_id": "L-1", "identity": "---", "name": "Synthetic Alpha"}],
        [{"right_row_id": "R-1", "identity": "---", "name": "Synthetic Alpha"}],
    )

    assert result.pairs == ()
    assert result.left_without_candidate == (2,)
    assert result.right_without_candidate == (2,)


def test_no_identifier_mapping_leaves_rows_for_later_stage(tmp_path: Path) -> None:
    result = _resolve(
        tmp_path,
        [{"left_row_id": "L-1", "name": "Synthetic Alpha"}],
        [{"right_row_id": "R-1", "name": "Synthetic Alpha"}],
        (NAME,),
    )

    assert result.pairs == ()
    assert result.left_without_candidate == (2,)
    assert result.right_without_candidate == (2,)


def test_rows_without_exact_identifier_remain_unresolved(tmp_path: Path) -> None:
    result = _resolve(
        tmp_path,
        [
            {"left_row_id": "L-1", "identity": "SYN-1", "name": "Synthetic Alpha"},
            {"left_row_id": "L-2", "identity": "SYN-2", "name": "Synthetic Beta"},
        ],
        [{"right_row_id": "R-1", "identity": "SYN1", "name": "Synthetic Alpha"}],
    )

    assert len(result.pairs) == 1
    assert result.pairs[0].decision is MatchDecision.MATCH
    assert result.left_without_candidate == (3,)
    assert result.right_without_candidate == ()


def test_rejects_normalized_fields_from_a_different_config() -> None:
    config = load_config("examples/basic-job.toml")
    loaded_left, loaded_right = load_sources(config)
    validated_left, validated_right = validate_sources(config, loaded_left, loaded_right)
    normalized_left, normalized_right = normalize_sources(config, validated_left, validated_right)
    different_field = replace(config.field_mappings[0], left_column="wrong_column")
    different_config = replace(config, field_mappings=(different_field, *config.field_mappings[1:]))

    with pytest.raises(ValueError, match="do not match the job configuration"):
        resolve_exact_identifiers(different_config, normalized_left, normalized_right)


def test_repeated_identifier_group_is_bounded_before_cartesian_explosion(tmp_path: Path) -> None:
    left = [
        {"left_row_id": f"L-{index}", "identity": "SYN-DUPLICATE", "name": "Synthetic Alpha"}
        for index in range(32)
    ]
    right = [
        {"right_row_id": f"R-{index}", "identity": "SYN-DUPLICATE", "name": "Synthetic Alpha"}
        for index in range(32)
    ]

    with pytest.raises(CandidateLimitError, match="more than 1000 pairs") as error:
        _resolve(tmp_path, left, right)

    assert "SYN-DUPLICATE" not in str(error.value)


def test_total_candidate_limit_fails_without_exposing_identifiers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(exact_baseline, "MAX_CANDIDATE_PAIRS", 1)

    with pytest.raises(CandidateLimitError, match="more than 1 candidate pairs") as error:
        _resolve(
            tmp_path,
            [
                {"left_row_id": "L-1", "identity": "SYN-SECRET-A", "name": "Synthetic Alpha"},
                {"left_row_id": "L-2", "identity": "SYN-SECRET-B", "name": "Synthetic Beta"},
            ],
            [
                {"right_row_id": "R-1", "identity": "SYNSECRETA", "name": "Synthetic Alpha"},
                {"right_row_id": "R-2", "identity": "SYNSECRETB", "name": "Synthetic Beta"},
            ],
        )

    assert "SECRET" not in str(error.value)

"""Behavioral tests for bounded name blocking before fuzzy scoring."""

from pathlib import Path

import pandas as pd
import pytest

import entity_resolution_engine.blocking as blocking
from entity_resolution_engine.blocking import (
    NameBlockingLimitError,
    NameBlockStrategy,
    generate_name_candidates,
)
from entity_resolution_engine.config import (
    EngineConfig,
    FieldMapping,
    FileType,
    SemanticFieldType,
    SourceConfig,
)
from entity_resolution_engine.decision import DecisionPolicy
from entity_resolution_engine.ingestion import LoadedSource
from entity_resolution_engine.normalization import normalize_sources
from entity_resolution_engine.validation import validate_sources


def _candidates(
    tmp_path: Path,
    left_names: list[str],
    right_names: list[str],
    *,
    semantic_type: SemanticFieldType = SemanticFieldType.PERSON_NAME,
    excluded: frozenset[tuple[int, int]] = frozenset(),
) -> blocking.NameBlockingResult:
    config = EngineConfig(
        left_source=SourceConfig(tmp_path / "left.csv", FileType.CSV, "row_id"),
        right_source=SourceConfig(tmp_path / "right.csv", FileType.CSV, "row_id"),
        field_mappings=(FieldMapping("name", "name", "name", semantic_type),),
        decision_policy=DecisionPolicy(),
    )
    left = LoadedSource(
        config.left_source,
        pd.DataFrame(
            {"row_id": [f"L-{index}" for index in range(len(left_names))], "name": left_names}
        ),
        tuple(range(2, len(left_names) + 2)),
    )
    right = LoadedSource(
        config.right_source,
        pd.DataFrame(
            {"row_id": [f"R-{index}" for index in range(len(right_names))], "name": right_names}
        ),
        tuple(range(2, len(right_names) + 2)),
    )
    normalized = normalize_sources(config, *validate_sources(config, left, right))
    return generate_name_candidates(*normalized, excluded_source_rows=excluded)


def test_complementary_anchors_find_different_name_typos_without_exact_ids(
    tmp_path: Path,
) -> None:
    result = _candidates(
        tmp_path,
        ["João da Silva", "Bruno Nunes", "Ana Luz"],
        ["Joao Silvaa", "Brunno Nunes", "Ana Luz"],
    )

    assert result.possible_pairs == 9
    assert [(pair.left_source_row, pair.right_source_row) for pair in result.candidates] == [
        (2, 2),
        (3, 3),
        (4, 4),
    ]
    assert [origin.strategy for origin in result.candidates[0].origins] == [
        NameBlockStrategy.FIRST_LAST_INITIAL
    ]
    assert [origin.strategy for origin in result.candidates[1].origins] == [
        NameBlockStrategy.LAST_FIRST_INITIAL
    ]
    assert {origin.strategy for origin in result.candidates[2].origins} == set(NameBlockStrategy)
    assert "João" not in repr(result)
    assert "L-0" not in repr(result)


def test_existing_exact_candidate_is_excluded_without_losing_other_name_candidate(
    tmp_path: Path,
) -> None:
    result = _candidates(
        tmp_path,
        ["João Silva"],
        ["Joao Silva", "Joao Silvaa"],
        excluded=frozenset({(2, 2)}),
    )

    assert [(pair.left_source_row, pair.right_source_row) for pair in result.candidates] == [(2, 3)]
    assert result.possible_pairs == 2


def test_missing_single_token_and_non_name_fields_do_not_create_candidates(
    tmp_path: Path,
) -> None:
    names = _candidates(tmp_path, ["---", "João"], ["---", "João"])
    text = _candidates(
        tmp_path,
        ["Synthetic Company"],
        ["Synthetic Company"],
        semantic_type=SemanticFieldType.TEXT,
    )

    assert names.candidates == ()
    assert text.candidates == ()


def test_common_name_key_is_bounded_without_exposing_the_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(blocking, "MAX_PAIRS_PER_NAME_KEY", 3)

    with pytest.raises(NameBlockingLimitError, match="more than 3 pairs") as error:
        _candidates(tmp_path, ["Synthetic Private"] * 2, ["Synthetic Private"] * 2)

    assert "Synthetic" not in str(error.value)
    assert "Private" not in str(error.value)


def test_total_new_candidate_limit_is_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(blocking, "MAX_NAME_CANDIDATE_PAIRS", 1)

    with pytest.raises(NameBlockingLimitError, match="more than 1 new candidate pairs"):
        _candidates(
            tmp_path,
            ["Synthetic Alpha", "Fabricated Beta"],
            ["Synthetic Alpha", "Fabricated Beta"],
        )

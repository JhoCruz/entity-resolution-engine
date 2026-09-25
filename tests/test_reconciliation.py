"""End-to-end tests for saved reconciliation decisions and local privacy views."""

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

import entity_resolution_engine.date_blocking as date_blocking
from entity_resolution_engine.cli import app
from entity_resolution_engine.config import load_config
from entity_resolution_engine.decision import MatchDecision
from entity_resolution_engine.reconciliation import reconcile
from entity_resolution_engine.reporting import ReportError, write_reports

runner = CliRunner()


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _job(tmp_path: Path, left: str, right: str) -> Path:
    (tmp_path / "left.csv").write_text(left, encoding="utf-8")
    (tmp_path / "right.csv").write_text(right, encoding="utf-8")
    config = tmp_path / "job.toml"
    config.write_text(
        """schema_version = 1
[sources.left]
path = "left.csv"
file_type = "csv"
record_id = "row_id"
[sources.right]
path = "right.csv"
file_type = "csv"
record_id = "row_id"
[[field_mappings]]
name = "name"
left_column = "name"
right_column = "name"
semantic_type = "person_name"
weight = 0.45
[[field_mappings]]
name = "id"
left_column = "id"
right_column = "id"
semantic_type = "identifier"
weight = 0.35
[[field_mappings]]
name = "date"
left_column = "date"
right_column = "date"
semantic_type = "date"
weight = 0.20
[thresholds]
automatic_match = 0.90
review = 0.70
""",
        encoding="utf-8",
    )
    return config


def test_reduced_report_scores_variants_without_leaking_source_values(tmp_path: Path) -> None:
    output = tmp_path / "reports" / "variants"
    response = runner.invoke(
        app,
        ["reconcile", "--config", "examples/name-variants-job.toml", "--output", str(output)],
    )

    assert response.exit_code == 0, response.output
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    assert (summary["matches"], summary["reviews"], summary["non_matches"]) == (0, 2, 0)
    assert summary["pairs_not_selected_unresolved"] == 6
    assert summary["left_rows_without_candidates"] == 2
    assert summary["fuzzy_thresholds_calibrated"] is False
    reviews = _jsonl(output / "reviews.jsonl")
    assert len(reviews) == 2
    assert all(item["stage"] == "name_similarity" for item in reviews)
    assert all(item["decision"] == "review" for item in reviews)
    assert all("identifier_conflict" in item["reasons"] for item in reviews)
    assert all(item["thresholds"]["status"] == "not_calibrated_not_applied" for item in reviews)
    assert all(0 < item["score"] < 1 for item in reviews)
    assert all([field["score"] for field in item["evidence"]][1:] == [0.0, 1.0] for item in reviews)
    assert not _jsonl(output / "non_matches.jsonl")
    assert len(_jsonl(output / "conflicts.jsonl")) == 2
    assert not (output / "full").exists()
    reduced = "".join(path.read_text(encoding="utf-8") for path in output.iterdir())
    for private_value in ("Ana Souza", "Bruno Martins", "SYN-", "A-001", "V-001"):
        assert private_value not in reduced
        assert private_value not in response.output
    assert "source_row" not in reduced
    assert "normalized" not in reduced
    assert len(reviews[0]["left_ref"]) == 32


def test_full_audit_links_original_and_normalized_rows_only_when_requested(
    tmp_path: Path,
) -> None:
    config = load_config("examples/name-variants-job.toml")
    result = reconcile(config)
    first = write_reports(config, result, tmp_path / "first", full_audit=True)
    second = write_reports(config, result, tmp_path / "second", full_audit=True)

    left = _jsonl(first / "full" / "normalized_left.jsonl")
    right = _jsonl(first / "full" / "normalized_right.jsonl")
    audit = _jsonl(first / "full" / "audit.jsonl")
    review = _jsonl(first / "reviews.jsonl")
    assert left[0]["fields"]["full_name"]["original"] == "Ana Souza"
    assert left[0]["fields"]["full_name"]["normalized"] == "ana souza"
    assert left[0]["source_record_id"] == "A-001"
    assert left[0]["row_ref"] == review[0]["left_ref"] == audit[0]["left_ref"]
    assert right[0]["row_ref"] == review[0]["right_ref"]
    assert audit[0]["left_record_id"] == "A-001"
    assert _jsonl(second / "reviews.jsonl")[0]["left_ref"] != review[0]["left_ref"]
    assert (first / "full" / "audit.jsonl").stat().st_mode & 0o777 == 0o600
    assert (first / "full").stat().st_mode & 0o777 == 0o700


def test_exact_matches_are_not_reintroduced_as_fuzzy_candidates(tmp_path: Path) -> None:
    path = _job(
        tmp_path,
        "row_id,name,id,date\nL-1,Ana Souza,SYN-1,2000-01-01\n",
        "row_id,name,id,date\nR-1,Ana Souza,SYN-1,2000-01-01\nR-2,Ana Souzax,SYN-2,2000-01-01\n",
    )
    config = load_config(path)
    result = reconcile(config)
    output = write_reports(config, result, tmp_path / "result")

    assert len(result.exact.pairs) == 1
    assert result.exact.pairs[0].decision is MatchDecision.MATCH
    assert result.scored == ()
    assert not _jsonl(output / "reviews.jsonl")
    assert len(_jsonl(output / "matches.jsonl")) == 1
    assert (
        json.loads((output / "summary.json").read_text(encoding="utf-8"))[
            "pairs_not_selected_unresolved"
        ]
        == 1
    )


def test_conflicting_exact_candidate_requires_review_in_conflicts_report(tmp_path: Path) -> None:
    path = _job(
        tmp_path,
        "row_id,name,id,date\nL-1,Ana Souza,SYN-1,2000-01-01\n",
        "row_id,name,id,date\nR-1,Ana Souza,SYN-1,2001-01-01\n",
    )
    config = load_config(path)
    output = write_reports(config, reconcile(config), tmp_path / "result")

    assert not _jsonl(output / "matches.jsonl")
    reviews = _jsonl(output / "reviews.jsonl")
    assert reviews == _jsonl(output / "conflicts.jsonl")
    assert reviews[0]["reasons"] == ["exact_identifier", "field_conflict"]
    assert reviews[0]["evidence"][2]["score"] == 0.0


def test_invalid_date_and_missing_identifier_do_not_inflate_weighted_score(
    tmp_path: Path,
) -> None:
    path = _job(
        tmp_path,
        "row_id,name,id,date\nL-1,Ana Souza,,bad-date\n",
        "row_id,name,id,date\nR-1,Ana Souzax,,2000-01-01\n",
    )
    config = load_config(path)
    pair = reconcile(config).scored[0]

    assert pair.decision is MatchDecision.REVIEW
    assert pair.score == pytest.approx(0.9473684210526316)
    assert [item.field.score for item in pair.evidence] == [pair.score, None, None]
    assert [reason.value for reason in pair.reasons] == [
        "uncalibrated_score",
        "invalid_field",
        "insufficient_evidence",
    ]


def test_reconcile_refuses_to_replace_an_existing_report(tmp_path: Path) -> None:
    config = load_config("examples/basic-job.toml")
    result = reconcile(config)
    output = tmp_path / "saved"
    write_reports(config, result, output)
    before = (output / "matches.jsonl").read_bytes()

    with pytest.raises(ReportError, match="already exists"):
        write_reports(config, result, output, full_audit=True)
    response = runner.invoke(
        app,
        ["reconcile", "--config", "examples/basic-job.toml", "--output", str(output)],
    )
    assert response.exit_code == 6
    assert "already exists" in response.output
    assert (output / "matches.jsonl").read_bytes() == before


def test_date_candidate_recovers_both_changed_name_anchors_for_review(tmp_path: Path) -> None:
    path = _job(
        tmp_path,
        "row_id,name,id,date\nL-1,Ana Souza,,2000-01-01\n",
        "row_id,name,id,date\nR-1,Zna Xouza,,2000-01-01\n",
    )
    config = load_config(path)
    result = reconcile(config)
    output = write_reports(config, result, tmp_path / "result")

    assert not result.names.candidates
    assert len(result.dates.candidates) == 1
    reviews = _jsonl(output / "reviews.jsonl")
    assert len(reviews) == 1
    assert reviews[0]["stage"] == "date_blocking"
    assert "date_only_candidate" in reviews[0]["reasons"]
    assert reviews[0]["evidence"][2]["score"] == 1.0
    assert not _jsonl(output / "matches.jsonl")


def test_shared_date_generates_reviews_for_unrelated_people(tmp_path: Path) -> None:
    path = _job(
        tmp_path,
        "row_id,name,id,date\nL-1,Ana Souza,SYN-A,2000-01-01\nL-2,Bruno Martins,SYN-B,2000-01-01\n",
        "row_id,name,id,date\nR-1,Zara Xavier,SYN-C,2000-01-01\nR-2,Hugo Violet,SYN-D,2000-01-01\n",
    )
    config = load_config(path)
    result = reconcile(config)

    assert len(result.dates.candidates) == 4
    assert len(result.scored) == 4
    assert all(item.decision is MatchDecision.REVIEW for item in result.scored)
    assert all("identifier_conflict" in item.reasons for item in result.scored)


def test_invalid_dates_do_not_generate_date_candidates(tmp_path: Path) -> None:
    path = _job(
        tmp_path,
        "row_id,name,id,date\nL-1,Ana Souza,,bad-date\n",
        "row_id,name,id,date\nR-1,Zara Xavier,,bad-date\n",
    )

    result = reconcile(load_config(path))
    assert not result.dates.candidates
    assert not result.scored


def test_common_date_key_is_bounded_without_disclosing_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(date_blocking, "MAX_PAIRS_PER_DATE_KEY", 3)
    path = _job(
        tmp_path,
        "row_id,name,id,date\nL-1,Ana Souza,,2000-01-01\nL-2,Bruno Martins,,2000-01-01\n",
        "row_id,name,id,date\nR-1,Zara Xavier,,2000-01-01\nR-2,Hugo Violet,,2000-01-01\n",
    )

    response = runner.invoke(
        app, ["reconcile", "--config", str(path), "--output", str(tmp_path / "out")]
    )
    assert response.exit_code == 5
    assert "Date field 'date' generates more than 3 pairs" in response.output
    assert "2000-01-01" not in response.output
    assert not (tmp_path / "out").exists()

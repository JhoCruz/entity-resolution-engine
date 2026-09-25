"""Check opt-in synthetic calibration, one-to-one safeguards, and held-out evidence."""

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from entity_resolution_engine.benchmark import generate_benchmark
from entity_resolution_engine.calibration import calibrate
from entity_resolution_engine.cli import app
from entity_resolution_engine.config import load_config
from entity_resolution_engine.decision import MatchDecision
from entity_resolution_engine.policy import (
    PolicyError,
    SyntheticPolicy,
    field_contract,
    load_policy,
)
from entity_resolution_engine.reconciliation import reconcile

runner = CliRunner()
CALIBRATION = Path("docs/evaluation/synthetic-policy.json")


def _job(tmp_path: Path, left: str, right: str) -> Path:
    (tmp_path / "left.csv").write_text(left, encoding="utf-8")
    (tmp_path / "right.csv").write_text(right, encoding="utf-8")
    path = tmp_path / "job.toml"
    path.write_text(
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
name = "identity"
left_column = "identity"
right_column = "identity"
semantic_type = "identifier"
weight = 0.35
[[field_mappings]]
name = "birth_date"
left_column = "birth_date"
right_column = "birth_date"
semantic_type = "date"
weight = 0.20
[thresholds]
automatic_match = 0.90
review = 0.70
""",
        encoding="utf-8",
    )
    return path


def _demo_policy(path: Path) -> SyntheticPolicy:
    config = load_config(path)
    return SyntheticPolicy(0.90, 0.62, True, field_contract(config))


def test_calibration_is_explicit_and_recovers_some_heldout_true_pairs(tmp_path: Path) -> None:
    directory = tmp_path / "benchmark"
    generate_benchmark(directory, size=80, seed=20260925)
    config = load_config(directory / "job.toml")
    policy = load_policy(CALIBRATION, config)
    baseline = reconcile(config)
    calibrated = reconcile(config, policy)

    assert sum(item.decision is MatchDecision.MATCH for item in baseline.scored) == 0
    assert sum(item.decision is MatchDecision.MATCH for item in calibrated.scored) == 7
    assert all(
        item.decision is MatchDecision.REVIEW
        for item in calibrated.scored
        if item.stage == "date_blocking"
    )
    output = tmp_path / "report"
    response = runner.invoke(
        app,
        [
            "reconcile",
            "--config",
            str(directory / "job.toml"),
            "--calibration",
            str(CALIBRATION.resolve()),
            "--output",
            str(output),
        ],
    )
    assert response.exit_code == 0, response.output
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    assert summary["matches"] == 30
    assert summary["calibration_source"] == "synthetic_tuning_only"
    assert summary["fuzzy_thresholds_calibrated"] is True
    assert "Synthetic demonstration policy applied" in response.output
    matches = [json.loads(line) for line in (output / "matches.jsonl").read_text().splitlines()]
    fuzzy = [item for item in matches if item["stage"] == "name_similarity"]
    assert len(fuzzy) == 7
    assert all(item["thresholds"]["status"] == "synthetic_tuning_only" for item in fuzzy)
    reduced = "".join(path.read_text(encoding="utf-8") for path in output.iterdir())
    assert "SYN-" not in reduced
    assert "L-0003" not in reduced


def test_thresholds_are_chosen_on_labeled_tuning_data_only(tmp_path: Path) -> None:
    directory = tmp_path / "tuning"
    generate_benchmark(directory, size=80, seed=20260924)
    config = load_config(directory / "job.toml")
    with (directory / "labels.csv").open(encoding="utf-8", newline="") as handle:
        truth = {(row["left_record_id"], row["right_record_id"]) for row in csv.DictReader(handle)}

    policy = calibrate(config, reconcile(config), truth)
    assert (policy.review, policy.automatic_match, policy.automatic_enabled) == (0.62, 0.90, True)
    assert policy == load_policy(CALIBRATION, config)


def test_competing_candidates_and_conflicting_identifiers_stay_in_review(tmp_path: Path) -> None:
    path = _job(
        tmp_path,
        "row_id,name,identity,birth_date\nL-1,Ana Souza,,2000-01-01\n",
        "row_id,name,identity,birth_date\nR-1,Ana Souzax,,2000-01-01\nR-2,Ana Souzy,,2000-01-01\n",
    )
    result = reconcile(load_config(path), _demo_policy(path))
    assert len(result.scored) == 2
    assert all(item.decision is MatchDecision.REVIEW for item in result.scored)

    conflicting = _job(
        tmp_path,
        "row_id,name,identity,birth_date\nL-1,Ana Souza,SYN-1,2000-01-01\n",
        "row_id,name,identity,birth_date\nR-1,Ana Souzax,SYN-2,2000-01-01\n",
    )
    pair = reconcile(load_config(conflicting), _demo_policy(conflicting)).scored[0]
    assert pair.decision is MatchDecision.REVIEW
    assert "identifier_conflict" in pair.reasons


def test_low_name_score_can_be_rejected_without_rejecting_unseen_pairs(tmp_path: Path) -> None:
    path = _job(
        tmp_path,
        "row_id,name,identity,birth_date\nL-1,Ana Souza,,\n",
        "row_id,name,identity,birth_date\nR-1,Ana Szzzzzzzzzzzzzz,,\n",
    )
    content = path.read_text(encoding="utf-8")
    identity_start = content.index('[[field_mappings]]\nname = "identity"')
    thresholds_start = content.index("[thresholds]")
    path.write_text(content[:identity_start] + content[thresholds_start:], encoding="utf-8")
    config = load_config(path)
    result = reconcile(config, _demo_policy(path))
    assert result.scored[0].score is not None
    assert result.scored[0].score < 0.62
    assert result.scored[0].decision is MatchDecision.NO_MATCH
    assert result.scored[0].reasons[-1] == "below_review_threshold"


def test_policy_rejects_mismatched_fields_and_bad_thresholds(tmp_path: Path) -> None:
    path = _job(
        tmp_path,
        "row_id,name,identity,birth_date\nL-1,Ana Souza,,2000-01-01\n",
        "row_id,name,identity,birth_date\nR-1,Ana Souzax,,2000-01-01\n",
    )
    config = load_config(path)
    policy = json.loads(CALIBRATION.read_text(encoding="utf-8"))
    policy["field_contract"][0][0] = "unexpected"
    mismatch = tmp_path / "mismatch.json"
    mismatch.write_text(json.dumps(policy), encoding="utf-8")
    with pytest.raises(PolicyError, match="differ"):
        load_policy(mismatch, config)

    policy["field_contract"][0][0] = "name"
    policy["thresholds"]["review"] = 1.0
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps(policy), encoding="utf-8")
    response = runner.invoke(
        app,
        [
            "reconcile",
            "--config",
            str(path),
            "--calibration",
            str(invalid),
            "--output",
            str(tmp_path / "report"),
        ],
    )
    assert response.exit_code == 2
    assert "Calibration error:" in response.output
    assert not (tmp_path / "report").exists()


def test_all_exact_matches_with_a_common_date_do_not_hit_date_candidate_cap(tmp_path: Path) -> None:
    header = "row_id,name,identity,birth_date\n"
    left = header + "".join(
        f"L-{index},Ana Person{index},SYN-{index},2000-01-01\n" for index in range(32)
    )
    right = header + "".join(
        f"R-{index},Ana Person{index},SYN-{index},2000-01-01\n" for index in range(32)
    )
    result = reconcile(load_config(_job(tmp_path, left, right)))
    assert len(result.exact.pairs) == 32
    assert not result.dates.candidates


def test_calibration_artifact_is_regenerated_from_tuning_then_final(tmp_path: Path) -> None:
    output = tmp_path / "policy.json"
    subprocess.run(
        [sys.executable, "scripts/calibrate_policy.py", "--output", str(output)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert output.read_bytes() == CALIBRATION.read_bytes()
    policy = json.loads(output.read_text(encoding="utf-8"))
    assert policy["tuning_seed"] != policy["final_seed"]
    assert policy["tuning_with_policy"]["false_positives"] == 0
    assert policy["heldout_final_with_policy"]["false_positives"] == 0
    assert policy["heldout_final_with_policy"]["true_positives"] == 30

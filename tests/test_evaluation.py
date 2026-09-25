"""Verify synthetic labels, meaningful metrics and a reproducible published artifact."""

import csv
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import duckdb
import pytest

from entity_resolution_engine.benchmark import generate_benchmark
from entity_resolution_engine.config import load_config
from entity_resolution_engine.evaluation import evaluate
from entity_resolution_engine.reconciliation import reconcile


def _labels(path: Path) -> set[tuple[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return {(row["left_record_id"], row["right_record_id"]) for row in csv.DictReader(handle)}


def test_synthetic_sources_are_reproducible_and_ground_truth_is_separate(tmp_path: Path) -> None:
    first, second = tmp_path / "first", tmp_path / "second"
    generate_benchmark(first, seed=101, size=32)
    generate_benchmark(second, seed=101, size=32)

    for name in ("left.csv", "right.csv", "job.toml", "labels.csv"):
        assert (first / name).read_bytes() == (second / name).read_bytes()
    assert "entity_key" not in (first / "left.csv").read_text(encoding="utf-8")
    assert "entity_key" not in (first / "right.csv").read_text(encoding="utf-8")
    assert _labels(first / "labels.csv")
    different = tmp_path / "different_seed"
    generate_benchmark(different, seed=102, size=32)
    assert (different / "left.csv").read_bytes() != (first / "left.csv").read_bytes()
    assert all("SYN-" in line for line in (first / "left.csv").read_text().splitlines()[1:])


def test_date_fallback_recovers_true_pairs_missed_by_name_anchors(tmp_path: Path) -> None:
    directory = tmp_path / "bench"
    generate_benchmark(directory, seed=20260925, size=80)
    result = reconcile(load_config(directory / "job.toml"))
    metrics = evaluate(result, _labels(directory / "labels.csv"))

    assert metrics.true_pairs == 63
    assert metrics.selected_true_pairs == 63
    assert metrics.blocking_recall == 1.0
    assert metrics.recall == pytest.approx(23 / 63)
    assert metrics.reviewed_true_pairs == 40
    assert metrics.false_negatives == 40
    assert metrics.false_positives == 0


def test_false_match_example_is_reported_without_input_name(tmp_path: Path) -> None:
    directory = tmp_path / "bench"
    generate_benchmark(directory, seed=20260925, size=80)
    result = reconcile(load_config(directory / "job.toml"))
    automatic = next(pair for pair in result.exact.pairs if pair.decision.value == "match")
    false_truth = {("L-UNKNOWN", "R-UNKNOWN")}
    metrics = evaluate(
        replace(result, exact=replace(result.exact, pairs=(automatic,))), false_truth
    )

    assert metrics.true_positives == 0
    assert metrics.false_positives == 1
    assert metrics.precision == metrics.recall == metrics.f1 == 0.0
    assert metrics.false_match_examples == (
        {
            "left_record_id": str(automatic.left_record_id),
            "right_record_id": str(automatic.right_record_id),
        },
    )
    assert "Ana" not in str(metrics.false_match_examples)


def test_published_metrics_are_regenerated_byte_for_byte(tmp_path: Path) -> None:
    output = tmp_path / "reproduced.json"
    process = subprocess.run(
        [sys.executable, "scripts/evaluate_benchmark.py", "--output", str(output)],
        capture_output=True,
        text=True,
        check=True,
    )

    assert output.read_bytes() == Path("docs/evaluation/baseline.json").read_bytes()
    artifact = json.loads(output.read_text(encoding="utf-8"))
    assert artifact["splits"]["tuning"]["seed"] != artifact["splits"]["final"]["seed"]
    assert "final: precision=" in process.stdout


def test_analytics_database_keeps_candidate_decisions_and_is_repeatable(tmp_path: Path) -> None:
    output, database = tmp_path / "metrics.json", tmp_path / "metrics.duckdb"
    command = [
        sys.executable,
        "scripts/evaluate_benchmark.py",
        "--output",
        str(output),
        "--database",
        str(database),
    ]
    subprocess.run(command, check=True, capture_output=True, text=True)
    subprocess.run(command, check=True, capture_output=True, text=True)

    with duckdb.connect(str(database), read_only=True) as connection:
        aggregates = connection.execute(
            "SELECT split, selected_pairs FROM evaluation_splits ORDER BY split"
        ).fetchall()
        candidate_rows = connection.execute(
            "SELECT split, COUNT(*) FROM candidate_decisions GROUP BY split ORDER BY split"
        ).fetchall()
        true_pairs = connection.execute(
            "SELECT COUNT(*) FROM candidate_decisions WHERE split='final' AND is_true_pair"
        ).fetchone()
    assert aggregates == [("final", 74), ("tuning", 87)]
    assert candidate_rows == aggregates
    assert true_pairs == (63,)

"""Regenerate held-out synthetic splits and save reproducible baseline metrics.

Run: uv run python scripts/evaluate_benchmark.py --output docs/evaluation/baseline.json
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory

import duckdb

from entity_resolution_engine.benchmark import generate_benchmark
from entity_resolution_engine.config import load_config
from entity_resolution_engine.evaluation import EvaluationMetrics, evaluate
from entity_resolution_engine.reconciliation import ReconciliationResult, reconcile

SPLIT_SEEDS = {"tuning": 20260924, "final": 20260925}


def _create_tables(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """CREATE TABLE IF NOT EXISTS evaluation_splits (
            split VARCHAR PRIMARY KEY, seed INTEGER, input_rows INTEGER,
            true_pairs INTEGER, selected_pairs INTEGER, precision DOUBLE, recall DOUBLE,
            f1 DOUBLE, blocking_recall DOUBLE, review_rate DOUBLE
        )"""
    )
    connection.execute(
        """CREATE TABLE IF NOT EXISTS candidate_decisions (
            split VARCHAR, seed INTEGER, left_record_id VARCHAR, right_record_id VARCHAR,
            stage VARCHAR, decision VARCHAR, score DOUBLE, is_true_pair BOOLEAN
        )"""
    )


def _store_split(
    connection: duckdb.DuckDBPyConnection,
    split: str,
    seed: int,
    size: int,
    result: ReconciliationResult,
    truth: set[tuple[str, str]],
    metrics: EvaluationMetrics,
) -> None:
    """Persist synthetic-only intermediate pairs and aggregate evaluation metrics."""
    connection.execute("DELETE FROM candidate_decisions WHERE split = ?", [split])
    connection.execute("DELETE FROM evaluation_splits WHERE split = ?", [split])
    connection.execute(
        "INSERT INTO evaluation_splits VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            split,
            seed,
            size,
            metrics.true_pairs,
            metrics.selected_pairs,
            metrics.precision,
            metrics.recall,
            metrics.f1,
            metrics.blocking_recall,
            metrics.review_rate,
        ],
    )
    exact_rows = [
        (
            split,
            seed,
            str(pair.left_record_id),
            str(pair.right_record_id),
            "exact_identifier",
            pair.decision.value,
            None,
            (str(pair.left_record_id), str(pair.right_record_id)) in truth,
        )
        for pair in result.exact.pairs
    ]
    scored_rows = [
        (
            split,
            seed,
            str(pair.left_record_id),
            str(pair.right_record_id),
            pair.stage,
            pair.decision.value,
            pair.score,
            (str(pair.left_record_id), str(pair.right_record_id)) in truth,
        )
        for pair in result.scored
    ]
    if exact_rows or scored_rows:
        connection.executemany(
            "INSERT INTO candidate_decisions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            exact_rows + scored_rows,
        )


def benchmark(*, size: int = 80, database: Path | None = None) -> dict[str, object]:
    """Regenerate and evaluate disjoint random splits without changing the engine."""
    splits: dict[str, object] = {}
    if database:
        database.parent.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(str(database)) if database else None
    try:
        if connection:
            _create_tables(connection)
        with TemporaryDirectory(prefix="entity-resolution-benchmark-") as temporary:
            for split, seed in SPLIT_SEEDS.items():
                directory = Path(temporary) / split
                generate_benchmark(directory, seed=seed, size=size)
                with (directory / "labels.csv").open(encoding="utf-8", newline="") as handle:
                    truth = {
                        (row["left_record_id"], row["right_record_id"])
                        for row in csv.DictReader(handle)
                    }
                result = reconcile(load_config(directory / "job.toml"))
                metrics = evaluate(result, truth)
                splits[split] = {"seed": seed, "metrics": asdict(metrics)}
                if connection:
                    _store_split(connection, split, seed, size, result, truth, metrics)
    finally:
        if connection:
            connection.close()
    return {
        "benchmark": "synthetic_brazilian_style_v1",
        "size_per_split": size,
        "method": "exact decisions plus review-only weighted name and date candidates",
        "thresholds_applied_to_name_scores": False,
        "splits": splits,
    }


def main() -> None:
    """Save and briefly describe a deterministic benchmark artifact."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--size", type=int, default=80)
    parser.add_argument("--database", type=Path, help="Optional local DuckDB analytics database.")
    args = parser.parse_args()
    artifact = benchmark(size=args.size, database=args.database)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    for split, value in artifact["splits"].items():
        metrics = value["metrics"]
        print(
            f"{split}: precision={metrics['precision']:.3f} "
            f"recall={metrics['recall']:.3f} "
            f"blocking_recall={metrics['blocking_recall']:.3f} "
            f"review_rate={metrics['review_rate']:.3f}"
        )
    print(f"Metrics written to {args.output}")


if __name__ == "__main__":
    main()

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

from entity_resolution_engine.benchmark import generate_benchmark
from entity_resolution_engine.config import load_config
from entity_resolution_engine.evaluation import evaluate
from entity_resolution_engine.reconciliation import reconcile

SPLIT_SEEDS = {"tuning": 20260924, "final": 20260925}


def benchmark(*, size: int = 80) -> dict[str, object]:
    """Regenerate and evaluate disjoint random splits without changing the engine."""
    splits: dict[str, object] = {}
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
            splits[split] = {"seed": seed, "metrics": asdict(evaluate(result, truth))}
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
    args = parser.parse_args()
    artifact = benchmark(size=args.size)
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

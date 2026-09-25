"""Tune a synthetic-only demonstration policy and evaluate it once on held-out labels.

Run: uv run python scripts/calibrate_policy.py --output docs/evaluation/synthetic-policy.json
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory

from entity_resolution_engine.benchmark import generate_benchmark
from entity_resolution_engine.calibration import calibrate
from entity_resolution_engine.config import load_config
from entity_resolution_engine.evaluation import evaluate
from entity_resolution_engine.reconciliation import reconcile

SPLITS = {"tuning": 20260924, "final": 20260925}


def _truth(directory: Path) -> set[tuple[str, str]]:
    with (directory / "labels.csv").open(encoding="utf-8", newline="") as handle:
        return {(row["left_record_id"], row["right_record_id"]) for row in csv.DictReader(handle)}


def calibrated_demo() -> dict[str, object]:
    """Choose thresholds on tuning labels; report held-out outcomes without changing them."""
    with TemporaryDirectory(prefix="entity-resolution-calibration-") as temporary:
        tuning = Path(temporary) / "tuning"
        generate_benchmark(tuning, seed=SPLITS["tuning"])
        config = load_config(tuning / "job.toml")
        truth = _truth(tuning)
        baseline = reconcile(config)
        policy = calibrate(config, baseline, truth)
        tuned = reconcile(config, policy)

        final = Path(temporary) / "final"
        generate_benchmark(final, seed=SPLITS["final"])
        final_config = load_config(final / "job.toml")
        final_result = reconcile(final_config, policy)
        final_truth = _truth(final)

        return {
            "schema_version": 1,
            "source": policy.source,
            "benchmark": "synthetic_brazilian_style_v2",
            "tuning_seed": SPLITS["tuning"],
            "final_seed": SPLITS["final"],
            "field_contract": [list(field) for field in policy.field_contract],
            "thresholds": {
                "automatic_match": policy.automatic_match,
                "review": policy.review,
                "automatic_enabled": policy.automatic_enabled,
            },
            "tuning_baseline": asdict(evaluate(baseline, truth)),
            "tuning_with_policy": asdict(evaluate(tuned, truth)),
            "heldout_final_with_policy": asdict(evaluate(final_result, final_truth)),
            "limitations": "Synthetic demonstration; no real-data reliability claim.",
        }


def main() -> None:
    """Save a reproducible, opt-in policy with full evaluation evidence."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    artifact = calibrated_demo()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    thresholds = artifact["thresholds"]
    print(
        f"Synthetic policy: review >= {thresholds['review']:.2f}, "
        f"automatic match >= {thresholds['automatic_match']:.2f}"
    )
    print(f"Policy and held-out metrics written to {args.output}")


if __name__ == "__main__":
    main()

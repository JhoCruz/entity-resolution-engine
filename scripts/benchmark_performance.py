"""Measure one local machine's runtime, Python allocations, and candidate reduction.

Run: uv run python scripts/benchmark_performance.py --output docs/evaluation/performance.json
"""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import tempfile
import time
import tracemalloc
from pathlib import Path

from entity_resolution_engine.benchmark import generate_benchmark
from entity_resolution_engine.config import load_config
from entity_resolution_engine.reconciliation import reconcile


def profile(sizes: list[int], *, repeats: int = 3) -> dict[str, object]:
    """Regenerate the same inputs and measure full reconciliation for each size."""
    if repeats < 1 or not sizes or any(size < 8 or size > 256 for size in sizes):
        raise ValueError("Use at least one size from 8 to 256 and at least one repeat.")
    observations: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="entity-resolution-performance-") as temporary:
        for size in sizes:
            durations: list[float] = []
            allocations: list[float] = []
            possible_pairs = selected_pairs = name_pairs = date_pairs = 0
            for repeat in range(repeats):
                directory = Path(temporary) / f"size-{size}-repeat-{repeat}"
                generate_benchmark(directory, size=size)
                config = load_config(directory / "job.toml")
                tracemalloc.start()
                started = time.perf_counter()
                try:
                    result = reconcile(config)
                    elapsed = time.perf_counter() - started
                    _, peak = tracemalloc.get_traced_memory()
                finally:
                    tracemalloc.stop()
                durations.append(elapsed)
                allocations.append(peak / 1024**2)
                possible_pairs = result.names.possible_pairs
                name_pairs = len(result.names.candidates)
                date_pairs = len(result.dates.candidates)
                selected_pairs = len(result.exact.pairs) + len(result.scored)
            observations.append(
                {
                    "left_rows": size,
                    "right_rows": result.right.row_count,
                    "possible_pairs": possible_pairs,
                    "selected_pairs": selected_pairs,
                    "name_candidates": name_pairs,
                    "date_candidates": date_pairs,
                    "candidate_reduction": 1 - selected_pairs / possible_pairs,
                    "median_runtime_seconds": round(statistics.median(durations), 4),
                    "median_traced_python_peak_mib": round(statistics.median(allocations), 4),
                }
            )
    return {
        "seed": 20260925,
        "repeats_per_size": repeats,
        "python": platform.python_version(),
        "system": platform.system(),
        "measurement": "full reconciliation with tracemalloc enabled",
        "memory_scope": "peak traced Python allocations; excludes untracked native allocations",
        "observations": observations,
    }


def main() -> None:
    """Write a machine-specific example artifact without claiming universal speed."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sizes", nargs="+", type=int, default=[40, 80, 160, 240])
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    artifact = profile(args.sizes, repeats=args.repeats)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for point in artifact["observations"]:
        print(
            f"left={point['left_rows']} right={point['right_rows']} "
            f"selected={point['selected_pairs']}/{point['possible_pairs']} "
            f"median_s={point['median_runtime_seconds']} "
            f"traced_peak_mib={point['median_traced_python_peak_mib']}"
        )
    print(f"Results written to {args.output}")


if __name__ == "__main__":
    main()

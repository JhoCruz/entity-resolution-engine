"""Verify the performance harness measures the complete job and candidate reduction."""

import json
import subprocess
import sys
from pathlib import Path


def test_local_performance_harness_reports_increasing_inputs(tmp_path: Path) -> None:
    output = tmp_path / "performance.json"
    subprocess.run(
        [
            sys.executable,
            "scripts/benchmark_performance.py",
            "--sizes",
            "8",
            "16",
            "--repeats",
            "1",
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    artifact = json.loads(output.read_text(encoding="utf-8"))
    first, second = artifact["observations"]
    assert [first["left_rows"], second["left_rows"]] == [8, 16]
    for point in (first, second):
        assert point["possible_pairs"] == point["left_rows"] * point["right_rows"]
        assert point["selected_pairs"] <= point["possible_pairs"]
        assert point["candidate_reduction"] == 1 - point["selected_pairs"] / point["possible_pairs"]
        assert point["median_runtime_seconds"] > 0
        assert point["median_traced_python_peak_mib"] > 0
    assert second["possible_pairs"] > first["possible_pairs"]
    assert "excludes untracked native allocations" in artifact["memory_scope"]

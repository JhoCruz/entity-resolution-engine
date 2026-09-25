"""Tests for the command-line entry point."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

import entity_resolution_engine.blocking as blocking
from entity_resolution_engine import __version__
from entity_resolution_engine.cli import app

runner = CliRunner()


def test_version_option() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == __version__


def test_doctor_reports_ready_environment() -> None:
    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert f"entity-resolution-engine {__version__}" in result.stdout
    assert "Default decision policy" in result.stdout
    assert result.stdout.rstrip().endswith("Environment ready.")


def test_check_config_reports_valid_contract() -> None:
    result = runner.invoke(app, ["check-config", "examples/basic-job.toml"])

    assert result.exit_code == 0
    assert "Configuration valid" in result.stdout
    assert "Left source: csv (record_id=customer_id)" in result.stdout
    assert "Right source: xlsx (record_id=row_id)" in result.stdout
    assert "Field mappings: 3" in result.stdout
    assert "review >= 0.70; automatic match >= 0.90" in result.stdout


def test_check_config_reports_actionable_error(tmp_path: Path) -> None:
    invalid_path = tmp_path / "invalid.toml"
    invalid_path.write_text("schema_version = 2", encoding="utf-8")

    result = runner.invoke(app, ["check-config", str(invalid_path)])

    assert result.exit_code == 2
    assert "Configuration error:" in result.output
    assert "configuration.sources must be a table" in result.output


def test_inspect_reports_valid_sources_without_record_values() -> None:
    result = runner.invoke(app, ["inspect", "--config", "examples/basic-job.toml"])

    assert result.exit_code == 0
    assert "Mapped fields (3): full_name, tax_id, birth_date" in result.stdout
    assert "Left source: valid | type=csv | rows=4" in result.stdout
    assert "Right source: valid | type=xlsx | worksheet=Customers | rows=4" in result.stdout
    assert "Validation status: valid" in result.stdout
    assert "Matching status: not run" in result.stdout
    assert "SYN-" not in result.stdout
    assert "Ana" not in result.stdout


def _write_inspection_config(tmp_path: Path, right_path: Path) -> Path:
    config_path = tmp_path / "job.toml"
    config_path.write_text(
        f"""
schema_version = 1

[sources.left]
path = "left.csv"
file_type = "csv"
record_id = "left_id"

[sources.right]
path = "{right_path.name}"
file_type = "csv"
record_id = "right_id"

[[field_mappings]]
name = "full_name"
left_column = "name"
right_column = "name"
semantic_type = "person_name"

[thresholds]
automatic_match = 0.90
review = 0.70
""".strip(),
        encoding="utf-8",
    )
    return config_path


def test_inspect_returns_nonzero_without_exposing_duplicate_identifier(tmp_path: Path) -> None:
    (tmp_path / "left.csv").write_text(
        "left_id,name\nL-001,Synthetic Left\n",
        encoding="utf-8",
    )
    right_path = tmp_path / "right.csv"
    right_path.write_text(
        "right_id,name\nPRIVATE-DUPLICATE,Synthetic One\nPRIVATE-DUPLICATE,Synthetic Two\n",
        encoding="utf-8",
    )
    config_path = _write_inspection_config(tmp_path, right_path)

    result = runner.invoke(app, ["inspect", "--config", str(config_path)])

    assert result.exit_code == 4
    assert "Validation error:" in result.output
    assert "duplicate record identifier" in result.output
    assert "right_id" in result.output
    assert "PRIVATE-DUPLICATE" not in result.output


def test_inspect_reports_ingestion_error(tmp_path: Path) -> None:
    (tmp_path / "left.csv").write_text(
        "left_id,name\nL-001,Synthetic Left\n",
        encoding="utf-8",
    )
    missing_right = tmp_path / "missing.csv"
    config_path = _write_inspection_config(tmp_path, missing_right)

    result = runner.invoke(app, ["inspect", "--config", str(config_path)])

    assert result.exit_code == 3
    assert "Ingestion error:" in result.output
    assert "file does not exist" in result.output


def test_inspect_reports_configuration_error(tmp_path: Path) -> None:
    invalid_path = tmp_path / "invalid.toml"
    invalid_path.write_text("schema_version = 2", encoding="utf-8")

    result = runner.invoke(app, ["inspect", "--config", str(invalid_path)])

    assert result.exit_code == 2
    assert "Configuration error:" in result.output


def test_baseline_resolves_documented_csv_xlsx_without_revealing_values() -> None:
    result = runner.invoke(app, ["baseline", "--config", "examples/basic-job.toml"])

    assert result.exit_code == 0
    assert "Candidate pairs: 4 | match: 4 | review: 0" in result.stdout
    assert "Rows without exact-ID candidates: left=0 | right=0" in result.stdout
    assert "Review reasons: none" in result.stdout
    assert "other pairs unresolved" in result.stdout
    assert "SYN-" not in result.stdout
    assert "Ana" not in result.stdout


def test_candidates_find_name_variations_without_revealing_source_values() -> None:
    result = runner.invoke(app, ["candidates", "--config", "examples/name-variants-job.toml"])

    assert result.exit_code == 0
    assert "Exact-ID candidates: 0 | new name candidates: 2" in result.stdout
    assert "Pairs not selected: 6 of 8" in result.stdout
    assert "first_token_last_initial=1" in result.stdout
    assert "last_token_first_initial=1" in result.stdout
    assert "fuzzy scoring has not run" in result.stdout
    assert "SYN-" not in result.stdout
    assert "Ana" not in result.stdout


def test_candidates_do_not_count_exact_identifier_pairs_twice() -> None:
    result = runner.invoke(app, ["candidates", "--config", "examples/basic-job.toml"])

    assert result.exit_code == 0
    assert "Exact-ID candidates: 4 | new name candidates: 0" in result.stdout
    assert "Pairs not selected: 12 of 16" in result.stdout


def test_candidates_bounded_common_name_key_does_not_expose_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(blocking, "MAX_PAIRS_PER_NAME_KEY", 3)
    (tmp_path / "left.csv").write_text(
        "left_id,name\nL-1,Synthetic Private\nL-2,Synthetic Private\n",
        encoding="utf-8",
    )
    (tmp_path / "right.csv").write_text(
        "right_id,name\nR-1,Synthetic Private\nR-2,Synthetic Private\n",
        encoding="utf-8",
    )

    config_path = _write_inspection_config(tmp_path, tmp_path / "right.csv")
    result = runner.invoke(app, ["candidates", "--config", str(config_path)])

    assert result.exit_code == 5
    assert "Candidate limit:" in result.output
    assert "Synthetic Private" not in result.output


def _write_baseline_config(tmp_path: Path) -> Path:
    path = _write_inspection_config(tmp_path, tmp_path / "right.csv")
    content = path.read_text(encoding="utf-8").replace(
        "[[field_mappings]]",
        '[[field_mappings]]\nname = "identity"\nleft_column = "identity"\n'
        'right_column = "identity"\nsemantic_type = "identifier"\n\n'
        "[[field_mappings]]",
        1,
    )
    path.write_text(content, encoding="utf-8")
    return path


def test_baseline_shows_review_reasons_without_record_values(tmp_path: Path) -> None:
    (tmp_path / "left.csv").write_text(
        "left_id,identity,name\nL-1,SYN-PRIVATE,Synthetic Alpha\nL-2,SYNPRIVATE,Synthetic Alpha\n",
        encoding="utf-8",
    )
    (tmp_path / "right.csv").write_text(
        "right_id,identity,name\nR-1,SYNPRIVATE,Synthetic Alpha\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["baseline", "--config", str(_write_baseline_config(tmp_path))])

    assert result.exit_code == 0
    assert "Candidate pairs: 2 | match: 0 | review: 2" in result.stdout
    assert "identifier_collision=2" in result.stdout
    assert "many_to_one=2" in result.stdout
    assert "SYN-PRIVATE" not in result.stdout
    assert "SYNPRIVATE" not in result.stdout
    assert "L-1" not in result.stdout


def test_baseline_rejects_unbounded_duplicate_group_without_values(tmp_path: Path) -> None:
    left = "left_id,identity,name\n" + "".join(
        f"L-{index},SYN-SENSITIVE,Synthetic Alpha\n" for index in range(32)
    )
    right = "right_id,identity,name\n" + "".join(
        f"R-{index},SYNSENSITIVE,Synthetic Alpha\n" for index in range(32)
    )
    (tmp_path / "left.csv").write_text(left, encoding="utf-8")
    (tmp_path / "right.csv").write_text(right, encoding="utf-8")

    result = runner.invoke(app, ["baseline", "--config", str(_write_baseline_config(tmp_path))])

    assert result.exit_code == 5
    assert "Candidate limit:" in result.output
    assert "more than 1000 pairs" in result.output
    assert "SYN-SENSITIVE" not in result.output
    assert "SYNSENSITIVE" not in result.output


def test_baseline_reports_bad_configuration(tmp_path: Path) -> None:
    invalid_path = tmp_path / "invalid.toml"
    invalid_path.write_text("schema_version = 2", encoding="utf-8")

    result = runner.invoke(app, ["baseline", "--config", str(invalid_path)])

    assert result.exit_code == 2
    assert "Configuration error:" in result.output


def test_baseline_reports_missing_input_file(tmp_path: Path) -> None:
    (tmp_path / "left.csv").write_text("left_id,name\nL-1,Synthetic Alpha\n", encoding="utf-8")
    config_path = _write_inspection_config(tmp_path, tmp_path / "missing.csv")

    result = runner.invoke(app, ["baseline", "--config", str(config_path)])

    assert result.exit_code == 3
    assert "Ingestion error:" in result.output


def test_baseline_reports_invalid_source_without_record_values(tmp_path: Path) -> None:
    (tmp_path / "left.csv").write_text("left_id,name\nL-1,Synthetic Alpha\n", encoding="utf-8")
    (tmp_path / "right.csv").write_text(
        "right_id,name\nPRIVATE-ID,Synthetic Alpha\nPRIVATE-ID,Synthetic Beta\n",
        encoding="utf-8",
    )
    config_path = _write_inspection_config(tmp_path, tmp_path / "right.csv")

    result = runner.invoke(app, ["baseline", "--config", str(config_path)])

    assert result.exit_code == 4
    assert "Validation error:" in result.output
    assert "duplicate record identifier" in result.output
    assert "PRIVATE-ID" not in result.output

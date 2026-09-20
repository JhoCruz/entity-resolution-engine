"""Tests for the command-line entry point."""

from pathlib import Path

from typer.testing import CliRunner

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

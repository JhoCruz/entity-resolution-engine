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

"""Tests for the command-line entry point."""

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

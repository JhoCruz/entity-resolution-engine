"""Command-line interface for the entity resolution engine."""

import platform
from pathlib import Path
from typing import Annotated

import typer

from entity_resolution_engine import __version__
from entity_resolution_engine.config import ConfigurationError, load_config
from entity_resolution_engine.decision import DecisionPolicy

app = typer.Typer(
    add_completion=False,
    invoke_without_command=True,
    no_args_is_help=True,
    help="Resolve duplicate entities in messy tabular data with auditable decisions.",
)


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option("--version", help="Show the installed version and exit.", is_eager=True),
    ] = False,
) -> None:
    """Entity Resolution Engine command-line interface."""
    if version:
        typer.echo(__version__)
        raise typer.Exit


@app.command()
def doctor() -> None:
    """Check that the initial package and decision policy can be loaded."""
    policy = DecisionPolicy()
    typer.echo(f"entity-resolution-engine {__version__}")
    typer.echo(f"Python {platform.python_version()}")
    typer.echo(
        "Default decision policy: "
        f"review >= {policy.review_threshold:.2f}; "
        f"automatic match >= {policy.automatic_match_threshold:.2f}"
    )
    typer.echo("Environment ready.")


@app.command("check-config")
def check_config(
    config_path: Annotated[
        Path,
        typer.Argument(help="Path to a TOML job configuration."),
    ],
) -> None:
    """Load a job configuration and report its validated contract."""
    try:
        config = load_config(config_path)
    except ConfigurationError as error:
        typer.echo(f"Configuration error: {error}", err=True)
        raise typer.Exit(code=2) from error

    typer.echo(f"Configuration valid: {config_path}")
    typer.echo(
        f"Left source: {config.left_source.file_type.value} "
        f"(record_id={config.left_source.record_id})"
    )
    typer.echo(
        f"Right source: {config.right_source.file_type.value} "
        f"(record_id={config.right_source.record_id})"
    )
    typer.echo(f"Field mappings: {len(config.field_mappings)}")
    typer.echo(
        "Decision thresholds: "
        f"review >= {config.decision_policy.review_threshold:.2f}; "
        f"automatic match >= {config.decision_policy.automatic_match_threshold:.2f}"
    )

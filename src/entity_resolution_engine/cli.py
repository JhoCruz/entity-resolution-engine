"""Command-line interface for the entity resolution engine."""

import platform
from typing import Annotated

import typer

from entity_resolution_engine import __version__
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

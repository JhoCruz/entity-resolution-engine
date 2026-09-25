"""Command-line interface for the entity resolution engine."""

import platform
from collections import Counter
from pathlib import Path
from typing import Annotated

import typer

from entity_resolution_engine import __version__
from entity_resolution_engine.blocking import NameBlockingLimitError, generate_name_candidates
from entity_resolution_engine.config import ConfigurationError, load_config
from entity_resolution_engine.decision import DecisionPolicy, MatchDecision
from entity_resolution_engine.exact_baseline import (
    CandidateLimitError,
    ExactReason,
    resolve_exact_identifiers,
)
from entity_resolution_engine.ingestion import IngestionError, load_sources
from entity_resolution_engine.normalization import normalize_sources
from entity_resolution_engine.reconciliation import reconcile
from entity_resolution_engine.reporting import ReportError, write_reports
from entity_resolution_engine.validation import (
    SourceValidationError,
    ValidatedSource,
    validate_sources,
)

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


def _report_source(label: str, source: ValidatedSource, mapped_field_count: int) -> None:
    loaded = source.loaded_source
    details = [
        f"type={loaded.source.file_type.value}",
        f"rows={loaded.row_count}",
        f"record_id={loaded.source.record_id}",
        f"mapped_fields={mapped_field_count}",
        f"warnings={len(source.warnings)}",
    ]
    if loaded.worksheet is not None:
        details.insert(1, f"worksheet={loaded.worksheet}")
    typer.echo(f"{label} source: valid | {' | '.join(details)}")


@app.command("inspect")
def inspect_job(
    config_path: Annotated[
        Path,
        typer.Option("--config", "-c", help="Path to a TOML job configuration."),
    ],
) -> None:
    """Load and validate both sources, then print a value-free structural summary."""
    try:
        config = load_config(config_path)
        left, right = load_sources(config)
        validated_left, validated_right = validate_sources(config, left, right)
    except ConfigurationError as error:
        typer.echo(f"Configuration error: {error}", err=True)
        raise typer.Exit(code=2) from error
    except IngestionError as error:
        typer.echo(f"Ingestion error: {error}", err=True)
        raise typer.Exit(code=3) from error
    except SourceValidationError as error:
        typer.echo(f"Validation error: {error}", err=True)
        raise typer.Exit(code=4) from error

    mapped_names = ", ".join(mapping.name for mapping in config.field_mappings)
    mapped_field_count = len(config.field_mappings)
    typer.echo(f"Inspection complete: {config_path}")
    typer.echo(f"Mapped fields ({mapped_field_count}): {mapped_names}")
    _report_source("Left", validated_left, mapped_field_count)
    _report_source("Right", validated_right, mapped_field_count)
    typer.echo("Validation status: valid")
    typer.echo("Matching status: not run")


@app.command("baseline")
def baseline_job(
    config_path: Annotated[
        Path,
        typer.Option("--config", "-c", help="Path to a TOML job configuration."),
    ],
) -> None:
    """Show safe counts for conservative exact-identifier candidate decisions."""
    try:
        config = load_config(config_path)
        loaded_left, loaded_right = load_sources(config)
        validated_left, validated_right = validate_sources(config, loaded_left, loaded_right)
        normalized_left, normalized_right = normalize_sources(
            config, validated_left, validated_right
        )
        result = resolve_exact_identifiers(config, normalized_left, normalized_right)
    except ConfigurationError as error:
        typer.echo(f"Configuration error: {error}", err=True)
        raise typer.Exit(code=2) from error
    except IngestionError as error:
        typer.echo(f"Ingestion error: {error}", err=True)
        raise typer.Exit(code=3) from error
    except SourceValidationError as error:
        typer.echo(f"Validation error: {error}", err=True)
        raise typer.Exit(code=4) from error
    except CandidateLimitError as error:
        typer.echo(f"Candidate limit: {error}", err=True)
        raise typer.Exit(code=5) from error

    matches = sum(pair.decision is MatchDecision.MATCH for pair in result.pairs)
    reviews = len(result.pairs) - matches
    review_reasons: Counter[ExactReason] = Counter(
        reason
        for pair in result.pairs
        if pair.decision is MatchDecision.REVIEW
        for reason in pair.reasons
        if reason is not ExactReason.EXACT_IDENTIFIER
    )
    reasons = ", ".join(
        f"{reason.value}={review_reasons[reason]}"
        for reason in ExactReason
        if review_reasons[reason]
    )
    typer.echo(f"Exact baseline complete: {config_path}")
    typer.echo(f"Candidate pairs: {len(result.pairs)} | match: {matches} | review: {reviews}")
    typer.echo(
        "Rows without exact-ID candidates: "
        f"left={len(result.left_without_candidate)} | right={len(result.right_without_candidate)}"
    )
    typer.echo(f"Review reasons: {reasons or 'none'}")
    typer.echo("Matching status: exact identifiers only; other pairs unresolved")


@app.command("candidates")
def candidates_job(
    config_path: Annotated[
        Path,
        typer.Option("--config", "-c", help="Path to a TOML job configuration."),
    ],
) -> None:
    """Count exact-ID and new name candidates without printing record values."""
    try:
        config = load_config(config_path)
        loaded_left, loaded_right = load_sources(config)
        validated_left, validated_right = validate_sources(config, loaded_left, loaded_right)
        normalized_left, normalized_right = normalize_sources(
            config, validated_left, validated_right
        )
        exact = resolve_exact_identifiers(config, normalized_left, normalized_right)
        names = generate_name_candidates(
            normalized_left,
            normalized_right,
            excluded_source_rows=frozenset(
                (pair.left_source_row, pair.right_source_row) for pair in exact.pairs
            ),
        )
    except ConfigurationError as error:
        typer.echo(f"Configuration error: {error}", err=True)
        raise typer.Exit(code=2) from error
    except IngestionError as error:
        typer.echo(f"Ingestion error: {error}", err=True)
        raise typer.Exit(code=3) from error
    except SourceValidationError as error:
        typer.echo(f"Validation error: {error}", err=True)
        raise typer.Exit(code=4) from error
    except (CandidateLimitError, NameBlockingLimitError) as error:
        typer.echo(f"Candidate limit: {error}", err=True)
        raise typer.Exit(code=5) from error

    selected = len(exact.pairs) + len(names.candidates)
    strategy_hits = Counter(
        origin.strategy for candidate in names.candidates for origin in candidate.origins
    )
    typer.echo(f"Candidate search complete: {config_path}")
    typer.echo(
        f"Exact-ID candidates: {len(exact.pairs)} | new name candidates: {len(names.candidates)}"
    )
    typer.echo(f"Pairs not selected: {names.possible_pairs - selected} of {names.possible_pairs}")
    typer.echo(
        "Name strategy hits: "
        + (
            ", ".join(f"{strategy.value}={strategy_hits[strategy]}" for strategy in strategy_hits)
            or "none"
        )
    )
    typer.echo("Name candidates are unresolved; fuzzy scoring has not run")


@app.command("reconcile")
def reconcile_job(
    config_path: Annotated[
        Path,
        typer.Option("--config", "-c", help="Path to a TOML job configuration."),
    ],
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="New directory for local report files."),
    ],
    full_audit: Annotated[
        bool,
        typer.Option("--full-audit", help="Also save original and normalized values locally."),
    ] = False,
) -> None:
    """Reconcile both sources and save reduced reports, with an optional full audit."""
    try:
        config = load_config(config_path)
        result = reconcile(config)
        saved = write_reports(config, result, output, full_audit=full_audit)
    except ConfigurationError as error:
        typer.echo(f"Configuration error: {error}", err=True)
        raise typer.Exit(code=2) from error
    except IngestionError as error:
        typer.echo(f"Ingestion error: {error}", err=True)
        raise typer.Exit(code=3) from error
    except SourceValidationError as error:
        typer.echo(f"Validation error: {error}", err=True)
        raise typer.Exit(code=4) from error
    except (CandidateLimitError, NameBlockingLimitError) as error:
        typer.echo(f"Candidate limit: {error}", err=True)
        raise typer.Exit(code=5) from error
    except ReportError as error:
        typer.echo(f"Report error: {error}", err=True)
        raise typer.Exit(code=6) from error

    matches = sum(pair.decision is MatchDecision.MATCH for pair in result.exact.pairs)
    reviews = len(result.exact.pairs) - matches + len(result.scored)
    typer.echo(f"Reconciliation complete: {saved}")
    typer.echo(f"Selected pairs: {len(result.exact.pairs) + len(result.scored)}")
    typer.echo(f"Matches: {matches} | reviews: {reviews}")
    typer.echo("Name candidates require review until scores are calibrated on labeled data.")
    typer.echo("Pairs not selected remain unresolved; see summary.json for counts.")
    typer.echo("Full audit saved locally." if full_audit else "Reduced report saved locally.")

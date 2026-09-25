"""Write separate reduced and opt-in full local reconciliation reports."""

from __future__ import annotations

import json
import math
import os
import secrets
import shutil
import tempfile
from collections.abc import Iterable, Iterator
from datetime import date, datetime
from pathlib import Path
from typing import Any, cast

import pandas as pd

from entity_resolution_engine.config import EngineConfig
from entity_resolution_engine.decision import MatchDecision
from entity_resolution_engine.exact_baseline import ExactPair, FieldEvidence
from entity_resolution_engine.normalization import (
    SOURCE_RECORD_ID_COLUMN,
    SOURCE_ROW_COLUMN,
    NormalizedSource,
)
from entity_resolution_engine.reconciliation import ReconciliationResult
from entity_resolution_engine.scoring import ScoredPair


class ReportError(ValueError):
    """Raised when a local report cannot be safely saved."""


def _json_value(value: object) -> object:
    """Convert spreadsheet scalar types to JSON without losing an original date."""
    if value is None or bool(pd.isna(cast(Any, value))):
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "item"):
        unwrapped: object = value.item()
        if unwrapped is not value:
            return _json_value(unwrapped)
    return str(value)


def _source_refs(source: NormalizedSource) -> dict[int, str]:
    refs: dict[int, str] = {}
    used: set[str] = set()
    for value in source.data[SOURCE_ROW_COLUMN].tolist():
        row = cast(int, value)
        reference = secrets.token_hex(16)
        while reference in used:
            reference = secrets.token_hex(16)
        used.add(reference)
        refs[row] = reference
    return refs


def _field(field: FieldEvidence, *, weight: float | None = None) -> dict[str, object]:
    result: dict[str, object] = {
        "name": field.name,
        "type": field.semantic_type.value,
        "outcome": field.outcome.value,
        "score": field.score,
        "left_issue": field.left_issue,
        "right_issue": field.right_issue,
    }
    if weight is not None:
        result["weight"] = weight
    return result


def _pair(
    pair: ExactPair | ScoredPair,
    left_refs: dict[int, str],
    right_refs: dict[int, str],
    config: EngineConfig,
) -> dict[str, object]:
    result: dict[str, object] = {
        "left_ref": left_refs[pair.left_source_row],
        "right_ref": right_refs[pair.right_source_row],
        "stage": "exact_identifier" if isinstance(pair, ExactPair) else pair.stage,
        "decision": pair.decision.value,
        "reasons": [reason.value for reason in pair.reasons],
    }
    if isinstance(pair, ExactPair):
        result["score"] = None
        result["matched_on"] = list(pair.matched_on)
        result["evidence"] = [_field(field) for field in pair.evidence]
    else:
        result["score"] = pair.score
        result["thresholds"] = {
            "review": config.decision_policy.review_threshold,
            "automatic_match": config.decision_policy.automatic_match_threshold,
            "status": "not_calibrated_not_applied",
        }
        result["origins"] = list(pair.origins)
        result["evidence"] = [_field(item.field, weight=item.weight) for item in pair.evidence]
    return result


def _write_json(path: Path, payload: object) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, allow_nan=False, indent=2)
        handle.write("\n")


def _write_jsonl(path: Path, records: Iterable[dict[str, object]]) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")


def _normalized_rows(source: NormalizedSource, refs: dict[int, str]) -> Iterator[dict[str, object]]:
    for index in range(source.row_count):
        row = int(cast(int, source.data[SOURCE_ROW_COLUMN].iat[index]))
        yield {
            "row_ref": refs[row],
            "source_row": row,
            "source_record_id": _json_value(source.data[SOURCE_RECORD_ID_COLUMN].iat[index]),
            "fields": {
                field.name: {
                    "original": _json_value(source.data[field.original_column].iat[index]),
                    "normalized": source.data[field.normalized_column].iat[index],
                    "transformations": list(
                        cast(tuple[str, ...], source.data[field.transformations_column].iat[index])
                    ),
                    "issue": source.data[field.issue_column].iat[index],
                }
                for field in source.fields
            },
        }


def _full_audit_pair(pair: ExactPair | ScoredPair, reduced: dict[str, object]) -> dict[str, object]:
    return {
        **reduced,
        "left_source_row": int(pair.left_source_row),
        "right_source_row": int(pair.right_source_row),
        "left_record_id": _json_value(pair.left_record_id),
        "right_record_id": _json_value(pair.right_record_id),
    }


def _has_conflict(row: dict[str, object]) -> bool:
    reasons = cast(list[str], row["reasons"])
    return any(
        reason in reasons
        for reason in ("field_conflict", "identifier_conflict", "structured_conflict")
    )


def write_reports(
    config: EngineConfig,
    result: ReconciliationResult,
    output: Path,
    *,
    full_audit: bool = False,
) -> Path:
    """Write per-run opaque refs by default, and source values only by explicit opt-in.

    Unselected pairs and rows with no candidate remain unresolved. The non-matches
    file contains only explicit decisions; it never lists an unseen Cartesian pair.
    """
    target = output.resolve()
    if output.is_symlink() or target.exists():
        raise ReportError("Output directory already exists; choose a new directory.")
    try:
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        stage = Path(tempfile.mkdtemp(prefix=".entity-resolution-", dir=target.parent))
    except OSError as error:
        raise ReportError("Could not create the output directory.") from error
    try:
        left_refs = _source_refs(result.left)
        right_refs = _source_refs(result.right)
        exact_pairs = result.exact.pairs
        pairs: tuple[ExactPair | ScoredPair, ...] = (*exact_pairs, *result.scored)
        rendered = tuple(_pair(pair, left_refs, right_refs, config) for pair in pairs)
        matches = [row for row in rendered if row["decision"] == MatchDecision.MATCH.value]
        reviews = [row for row in rendered if row["decision"] == MatchDecision.REVIEW.value]
        non_matches = [row for row in rendered if row["decision"] == MatchDecision.NO_MATCH.value]
        conflicts = [row for row in rendered if _has_conflict(row)]
        selected = len(pairs)
        left_rows = {pair.left_source_row for pair in pairs}
        right_rows = {pair.right_source_row for pair in pairs}
        summary = {
            "left_rows": result.left.row_count,
            "right_rows": result.right.row_count,
            "possible_pairs": result.names.possible_pairs,
            "selected_pairs": selected,
            "name_candidates": len(result.names.candidates),
            "date_candidates": len(result.dates.candidates),
            "pairs_not_selected_unresolved": result.names.possible_pairs - selected,
            "left_rows_without_candidates": result.left.row_count - len(left_rows),
            "right_rows_without_candidates": result.right.row_count - len(right_rows),
            "matches": len(matches),
            "reviews": len(reviews),
            "non_matches": len(non_matches),
            "conflicts_subset_of_reviews": len(conflicts),
            "fuzzy_thresholds_calibrated": False,
            "full_audit_included": full_audit,
        }
        _write_json(stage / "summary.json", summary)
        for name, rows in (
            ("matches.jsonl", matches),
            ("reviews.jsonl", reviews),
            ("non_matches.jsonl", non_matches),
            ("conflicts.jsonl", conflicts),
        ):
            _write_jsonl(stage / name, rows)
        if full_audit:
            audit_dir = stage / "full"
            audit_dir.mkdir(mode=0o700)
            _write_jsonl(
                audit_dir / "normalized_left.jsonl", _normalized_rows(result.left, left_refs)
            )
            _write_jsonl(
                audit_dir / "normalized_right.jsonl", _normalized_rows(result.right, right_refs)
            )
            _write_jsonl(
                audit_dir / "audit.jsonl",
                (_full_audit_pair(pair, row) for pair, row in zip(pairs, rendered, strict=True)),
            )
        stage.rename(target)
    except (OSError, ValueError, TypeError) as error:
        raise ReportError("Could not write report to the requested location.") from error
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return target

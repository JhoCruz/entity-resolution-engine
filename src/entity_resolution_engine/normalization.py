"""Create auditable comparison values without mutating validated source data."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, time
from enum import StrEnum
from typing import Any, cast

import pandas as pd

from entity_resolution_engine.config import EngineConfig, SemanticFieldType
from entity_resolution_engine.validation import ValidatedSource

SOURCE_RECORD_ID_COLUMN = "source_record_id"
SOURCE_ROW_COLUMN = "source_row"
_ISO_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_LOCAL_DATE = re.compile(r"([0-9]{1,2})[./-]([0-9]{1,2})[./-]([0-9]{4})")
_PHONE_NUMBER = re.compile(r"\+?[0-9(). -]+", re.ASCII)
_PHONE_EXTENSION = re.compile(r"\s*(?:ext\.?|x)\s*([0-9]+)$", re.IGNORECASE | re.ASCII)
_EMAIL_ATOM = r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+"
_EMAIL_LABEL = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
_EMAIL = re.compile(
    rf"(?P<local>{_EMAIL_ATOM}(?:\.{_EMAIL_ATOM})*)@"
    rf"(?P<domain>{_EMAIL_LABEL}(?:\.{_EMAIL_LABEL})*)",
    re.ASCII,
)


class NormalizationStep(StrEnum):
    """Stable names for transformations applied to a comparison value."""

    COERCE_TO_TEXT = "coerce_to_text"
    UNICODE_NFKC = "unicode_nfkc"
    CASE_FOLD = "case_fold"
    PUNCTUATION_TO_SPACE = "punctuation_to_space"
    WHITESPACE_COLLAPSE = "whitespace_collapse"
    DIACRITICS_REMOVED = "diacritics_removed"
    NON_ALPHANUMERIC_REMOVED = "non_alphanumeric_removed"
    OUTER_WHITESPACE_TRIM = "outer_whitespace_trim"
    PHONE_FORMATTING_REMOVED = "phone_formatting_removed"
    PHONE_EXTENSION_CANONICALIZED = "phone_extension_canonicalized"
    DATETIME_TO_DATE = "datetime_to_date"
    EMAIL_DOMAIN_LOWERCASE = "email_domain_lowercase"


class NormalizationIssue(StrEnum):
    """Reasons a present value cannot safely produce a comparison key."""

    UNSUPPORTED_PHONE = "unsupported_phone"
    AMBIGUOUS_DATE = "ambiguous_date"
    INVALID_DATE = "invalid_date"
    UNSUPPORTED_DATE = "unsupported_date"
    UNSUPPORTED_EMAIL = "unsupported_email"


@dataclass(frozen=True, slots=True)
class NormalizedValue:
    """An original value, comparison key, ordered transformations, and optional issue."""

    original: object
    normalized: str | None
    transformations: tuple[NormalizationStep, ...] = ()
    issue: NormalizationIssue | None = None


@dataclass(frozen=True, slots=True)
class NormalizedField:
    """Column metadata for one logical field in a normalized source table."""

    name: str
    source_column: str
    semantic_type: SemanticFieldType
    original_column: str
    normalized_column: str
    transformations_column: str
    issue_column: str


@dataclass(frozen=True, slots=True, eq=False)
class NormalizedSource:
    """A validated source plus a side-by-side, audit-friendly comparison table."""

    validated_source: ValidatedSource
    data: pd.DataFrame
    fields: tuple[NormalizedField, ...]

    @property
    def row_count(self) -> int:
        """Return the number of normalized source rows."""
        return len(self.data)


def _is_missing(value: object) -> bool:
    return bool(pd.isna(cast(Any, value)))


def _punctuation_to_space(value: str) -> str:
    return "".join(
        " " if unicodedata.category(character).startswith("P") else character for character in value
    )


def normalize_text(value: object) -> NormalizedValue:
    """Apply the transparent baseline text transformations in a stable order."""
    if not pd.api.types.is_scalar(value):
        raise TypeError("Normalization accepts scalar values only.")
    if _is_missing(value):
        return NormalizedValue(original=value, normalized=None)

    transformations: list[NormalizationStep] = []
    if isinstance(value, str):
        normalized = value
    else:
        normalized = str(value)
        transformations.append(NormalizationStep.COERCE_TO_TEXT)

    unicode_normalized = unicodedata.normalize("NFKC", normalized)
    if unicode_normalized != normalized:
        normalized = unicode_normalized
        transformations.append(NormalizationStep.UNICODE_NFKC)

    case_folded = normalized.casefold()
    if case_folded != normalized:
        normalized = case_folded
        transformations.append(NormalizationStep.CASE_FOLD)

    punctuation_normalized = _punctuation_to_space(normalized)
    if punctuation_normalized != normalized:
        normalized = punctuation_normalized
        transformations.append(NormalizationStep.PUNCTUATION_TO_SPACE)

    whitespace_normalized = " ".join(normalized.split())
    if whitespace_normalized != normalized:
        normalized = whitespace_normalized
        transformations.append(NormalizationStep.WHITESPACE_COLLAPSE)

    return NormalizedValue(
        original=value,
        normalized=normalized,
        transformations=tuple(transformations),
    )


def _record_semantic_transformation(
    value: NormalizedValue,
    normalized: str,
    step: NormalizationStep,
) -> NormalizedValue:
    if normalized == value.normalized:
        return value
    return NormalizedValue(
        original=value.original,
        normalized=normalized,
        transformations=(*value.transformations, step),
    )


def _prepare_structured_text(value: object, *, nfkc: bool = True) -> NormalizedValue:
    """Keep syntax significant for dates, phones, and e-mails."""
    if not pd.api.types.is_scalar(value):
        raise TypeError("Normalization accepts scalar values only.")
    if _is_missing(value):
        return NormalizedValue(original=value, normalized=None)

    transformations: list[NormalizationStep] = []
    if isinstance(value, str):
        normalized = value
    else:
        normalized = str(value)
        transformations.append(NormalizationStep.COERCE_TO_TEXT)

    if nfkc:
        unicode_normalized = unicodedata.normalize("NFKC", normalized)
        if unicode_normalized != normalized:
            normalized = unicode_normalized
            transformations.append(NormalizationStep.UNICODE_NFKC)

    stripped = normalized.strip()
    if stripped != normalized:
        normalized = stripped
        transformations.append(NormalizationStep.OUTER_WHITESPACE_TRIM)

    return NormalizedValue(value, normalized, tuple(transformations))


def _with_issue(value: NormalizedValue, issue: NormalizationIssue) -> NormalizedValue:
    return NormalizedValue(value.original, None, value.transformations, issue)


def normalize_phone(value: object) -> NormalizedValue:
    """Keep explicitly international and national numbers distinct, including extensions."""
    prepared = _prepare_structured_text(value)
    if prepared.normalized is None:
        return prepared

    original_text = prepared.normalized
    extension_match = _PHONE_EXTENSION.search(original_text)
    number = original_text[: extension_match.start()] if extension_match else original_text
    if not _PHONE_NUMBER.fullmatch(number):
        return _with_issue(prepared, NormalizationIssue.UNSUPPORTED_PHONE)

    depth = 0
    for character in number:
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
        if depth < 0:
            return _with_issue(prepared, NormalizationIssue.UNSUPPORTED_PHONE)
    if depth:
        return _with_issue(prepared, NormalizationIssue.UNSUPPORTED_PHONE)

    digits = "".join(character for character in number if character.isdigit())
    if not 3 <= len(digits) <= 15:
        return _with_issue(prepared, NormalizationIssue.UNSUPPORTED_PHONE)

    canonical_number = ("+" if number.startswith("+") else "") + digits
    original_suffix = original_text[len(number) :]
    result = _record_semantic_transformation(
        prepared,
        canonical_number + original_suffix,
        NormalizationStep.PHONE_FORMATTING_REMOVED,
    )
    if extension_match:
        result = _record_semantic_transformation(
            result,
            canonical_number + "x" + extension_match.group(1),
            NormalizationStep.PHONE_EXTENSION_CANONICALIZED,
        )
    return result


def normalize_date(value: object) -> NormalizedValue:
    """Accept only explicit ISO calendar dates or date-typed cells."""
    if isinstance(value, datetime):
        if value.tzinfo is not None or value.time() != time.min:
            return _with_issue(NormalizedValue(value, None), NormalizationIssue.UNSUPPORTED_DATE)
        return NormalizedValue(
            value,
            value.date().isoformat(),
            (NormalizationStep.COERCE_TO_TEXT, NormalizationStep.DATETIME_TO_DATE),
        )
    if isinstance(value, date):
        return NormalizedValue(value, value.isoformat(), (NormalizationStep.COERCE_TO_TEXT,))

    prepared = _prepare_structured_text(value)
    if prepared.normalized is None:
        return prepared
    if _ISO_DATE.fullmatch(prepared.normalized):
        try:
            date.fromisoformat(prepared.normalized)
        except ValueError:
            return _with_issue(prepared, NormalizationIssue.INVALID_DATE)
        return prepared

    local = _LOCAL_DATE.fullmatch(prepared.normalized)
    if local and all(1 <= int(part) <= 12 for part in local.groups()[:2]):
        return _with_issue(prepared, NormalizationIssue.AMBIGUOUS_DATE)
    return _with_issue(prepared, NormalizationIssue.UNSUPPORTED_DATE)


def normalize_email(value: object) -> NormalizedValue:
    """Preserve the mailbox local part and lowercase only its ASCII domain."""
    prepared = _prepare_structured_text(value, nfkc=False)
    if prepared.normalized is None:
        return prepared

    matched = _EMAIL.fullmatch(prepared.normalized)
    if matched is None or len(matched.group("local")) > 64 or len(prepared.normalized) > 254:
        return _with_issue(prepared, NormalizationIssue.UNSUPPORTED_EMAIL)

    return _record_semantic_transformation(
        prepared,
        matched.group("local") + "@" + matched.group("domain").lower(),
        NormalizationStep.EMAIL_DOMAIN_LOWERCASE,
    )


def normalize_person_name(value: object) -> NormalizedValue:
    """Create a diacritic-insensitive name key without changing token order."""
    baseline = normalize_text(value)
    if baseline.normalized is None:
        return baseline

    decomposed = unicodedata.normalize("NFD", baseline.normalized)
    without_diacritics = "".join(
        character for character in decomposed if not unicodedata.category(character).startswith("M")
    )
    normalized = unicodedata.normalize("NFC", without_diacritics)
    return _record_semantic_transformation(
        baseline,
        normalized,
        NormalizationStep.DIACRITICS_REMOVED,
    )


def normalize_identifier(value: object) -> NormalizedValue:
    """Create a generic identifier key containing only Unicode letters and digits."""
    baseline = normalize_text(value)
    if baseline.normalized is None:
        return baseline

    normalized = "".join(character for character in baseline.normalized if character.isalnum())
    return _record_semantic_transformation(
        baseline,
        normalized,
        NormalizationStep.NON_ALPHANUMERIC_REMOVED,
    )


def normalize_semantic_value(
    value: object,
    semantic_type: SemanticFieldType,
) -> NormalizedValue:
    """Dispatch to a semantic normalizer while retaining the baseline as the safe fallback."""
    if semantic_type is SemanticFieldType.PERSON_NAME:
        return normalize_person_name(value)
    if semantic_type is SemanticFieldType.IDENTIFIER:
        return normalize_identifier(value)
    if semantic_type is SemanticFieldType.PHONE:
        return normalize_phone(value)
    if semantic_type is SemanticFieldType.DATE:
        return normalize_date(value)
    if semantic_type is SemanticFieldType.EMAIL:
        return normalize_email(value)
    return normalize_text(value)


def _field_metadata(
    name: str,
    source_column: str,
    semantic_type: SemanticFieldType,
) -> NormalizedField:
    return NormalizedField(
        name=name,
        source_column=source_column,
        semantic_type=semantic_type,
        original_column=f"{name}_original",
        normalized_column=f"{name}_normalized",
        transformations_column=f"{name}_transformations",
        issue_column=f"{name}_issue",
    )


def _normalize_source(
    source: ValidatedSource,
    fields: tuple[NormalizedField, ...],
) -> NormalizedSource:
    loaded = source.loaded_source
    normalized_data = pd.DataFrame(
        {
            SOURCE_RECORD_ID_COLUMN: pd.Series(
                loaded.data[loaded.source.record_id].tolist(),
                dtype=object,
            ),
            SOURCE_ROW_COLUMN: pd.Series(loaded.source_rows, dtype="int64"),
        }
    )

    for field in fields:
        results = tuple(
            normalize_semantic_value(value, field.semantic_type)
            for value in loaded.data[field.source_column].tolist()
        )
        normalized_data[field.original_column] = pd.Series(
            [result.original for result in results],
            dtype=object,
        )
        normalized_data[field.normalized_column] = pd.Series(
            [result.normalized for result in results],
            dtype=object,
        )
        normalized_data[field.transformations_column] = pd.Series(
            [tuple(step.value for step in result.transformations) for result in results],
            dtype=object,
        )
        normalized_data[field.issue_column] = pd.Series(
            [result.issue.value if result.issue else None for result in results],
            dtype=object,
        )

    return NormalizedSource(
        validated_source=source,
        data=normalized_data,
        fields=fields,
    )


def normalize_sources(
    config: EngineConfig,
    left: ValidatedSource,
    right: ValidatedSource,
) -> tuple[NormalizedSource, NormalizedSource]:
    """Normalize mapped fields from both validated sources without changing their data frames."""
    left_fields = tuple(
        _field_metadata(mapping.name, mapping.left_column, mapping.semantic_type)
        for mapping in config.field_mappings
    )
    right_fields = tuple(
        _field_metadata(mapping.name, mapping.right_column, mapping.semantic_type)
        for mapping in config.field_mappings
    )
    return (
        _normalize_source(left, left_fields),
        _normalize_source(right, right_fields),
    )


__all__ = [
    "SOURCE_RECORD_ID_COLUMN",
    "SOURCE_ROW_COLUMN",
    "NormalizationIssue",
    "NormalizationStep",
    "NormalizedField",
    "NormalizedSource",
    "NormalizedValue",
    "normalize_date",
    "normalize_email",
    "normalize_identifier",
    "normalize_person_name",
    "normalize_phone",
    "normalize_semantic_value",
    "normalize_sources",
    "normalize_text",
]

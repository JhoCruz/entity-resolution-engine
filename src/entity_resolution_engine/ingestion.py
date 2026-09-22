"""Load configured CSV and XLSX sources without normalizing their values."""

from __future__ import annotations

import stat
from dataclasses import dataclass
from zipfile import BadZipFile

import pandas as pd

from entity_resolution_engine.config import EngineConfig, FileType, SourceConfig


class IngestionError(ValueError):
    """Raised when a configured source cannot be loaded safely."""


@dataclass(frozen=True, slots=True, eq=False)
class LoadedSource:
    """Tabular source data and its original logical row numbers."""

    source: SourceConfig
    data: pd.DataFrame
    source_rows: tuple[int, ...]
    worksheet: str | None = None

    @property
    def row_count(self) -> int:
        """Return the number of loaded data rows."""
        return len(self.data)


def _error(source: SourceConfig, detail: str) -> IngestionError:
    return IngestionError(f"Cannot load source '{source.path}': {detail}")


def _check_source_file(source: SourceConfig) -> None:
    try:
        file_status = source.path.stat()
    except FileNotFoundError as error:
        raise _error(source, "file does not exist.") from error
    except OSError as error:
        detail = error.strerror or str(error)
        raise _error(source, f"file metadata is unavailable: {detail}.") from error

    if not stat.S_ISREG(file_status.st_mode):
        raise _error(source, "path is not a regular file.")
    if file_status.st_size == 0:
        raise _error(source, "file is empty.")


def _read_csv(source: SourceConfig) -> pd.DataFrame:
    try:
        return pd.read_csv(
            source.path,
            sep=source.delimiter,
            encoding=source.encoding,
            header=None,
            dtype=object,
            keep_default_na=False,
            na_filter=False,
        )
    except UnicodeDecodeError as error:
        raise _error(
            source,
            f"CSV bytes cannot be decoded with encoding '{source.encoding}'.",
        ) from error
    except pd.errors.EmptyDataError as error:
        raise _error(source, "CSV contains no columns or rows.") from error
    except pd.errors.ParserError as error:
        raise _error(source, f"CSV is malformed: {error}.") from error
    except OSError as error:
        detail = error.strerror or str(error)
        raise _error(source, f"CSV could not be read: {detail}.") from error


def _read_xlsx(source: SourceConfig) -> tuple[pd.DataFrame, str]:
    try:
        with pd.ExcelFile(source.path, engine="openpyxl") as workbook:
            worksheets = tuple(workbook.sheet_names)
            if not worksheets:
                raise _error(source, "workbook contains no worksheets.")

            worksheet = source.worksheet or str(worksheets[0])
            if worksheet not in worksheets:
                available = ", ".join(repr(name) for name in worksheets)
                raise _error(
                    source,
                    f"worksheet '{worksheet}' was not found; available worksheets: {available}.",
                )

            data = pd.read_excel(
                workbook,
                sheet_name=worksheet,
                header=None,
                dtype=object,
                keep_default_na=False,
                na_filter=False,
            )
    except IngestionError:
        raise
    except (OSError, ValueError, BadZipFile) as error:
        raise _error(source, f"XLSX could not be read: {error}.") from error

    return data, worksheet


def load_source(source: SourceConfig) -> LoadedSource:
    """Load one configured source while preserving its cell values and row provenance."""
    _check_source_file(source)

    if source.file_type is FileType.CSV:
        data = _read_csv(source)
        worksheet = None
    elif source.file_type is FileType.XLSX:
        data, worksheet = _read_xlsx(source)
    else:  # pragma: no cover - FileType prevents unsupported values at the contract boundary
        raise _error(source, f"unsupported file type '{source.file_type}'.")

    if not data.empty:
        # A regular pandas header silently renames duplicates (e.g. name -> name.1).
        # Parsing it as a row lets validation see the original column names.
        headers = data.iloc[0].tolist()
        data = data.iloc[1:].reset_index(drop=True)
        data.columns = headers

    if data.empty:
        raise _error(source, "source contains no data rows.")

    source_rows = tuple(range(2, len(data) + 2))
    return LoadedSource(
        source=source,
        data=data,
        source_rows=source_rows,
        worksheet=worksheet,
    )


def load_sources(config: EngineConfig) -> tuple[LoadedSource, LoadedSource]:
    """Load the left and right sources from one validated engine configuration."""
    return load_source(config.left_source), load_source(config.right_source)


__all__ = ["IngestionError", "LoadedSource", "load_source", "load_sources"]

"""Auditable entity resolution for messy tabular data."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("entity-resolution-engine")
except PackageNotFoundError:  # pragma: no cover - only used outside an installed environment
    __version__ = "0.1.0.dev0"

__all__ = ["__version__"]

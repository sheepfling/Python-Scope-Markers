"""Stable programmatic API for scope-marker formatting."""

from ._implementation import (
    FileInspection,
    ScopeBoundary,
    __version__,
    discover_python_files,
    format_source,
    inspect_file,
    process_file,
    python_files,
)

__all__ = (
    "FileInspection",
    "ScopeBoundary",
    "__version__",
    "discover_python_files",
    "format_source",
    "inspect_file",
    "process_file",
    "python_files",
)

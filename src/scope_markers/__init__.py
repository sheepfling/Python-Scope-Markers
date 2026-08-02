"""Public package interface for the scope-marker formatter."""

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
from .cli import main

__all__ = (
    "FileInspection",
    "ScopeBoundary",
    "__version__",
    "discover_python_files",
    "format_source",
    "inspect_file",
    "main",
    "process_file",
    "python_files",
)

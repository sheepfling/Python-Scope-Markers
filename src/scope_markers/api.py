"""Stable programmatic API for scope-marker formatting.

This module is the supported import boundary for library users. The
implementation remains in a private module so formatting internals can evolve
without requiring callers to import private names directly. Use
``format_source`` for in-memory text, ``inspect_file`` for read-only file
inspection, ``process_file`` for checking or rewriting one file, and
``discover_python_files``/``python_files`` for discovery. Pass
``include_stubs=True`` to the discovery functions when `.pyi` files belong in
the result, or pass ``indent_width`` to formatting or file-inspection functions
to normalize logical block indentation before markers are regenerated.
"""

from ._implementation import (
    FileInspection,
    ScopeBoundary,
    ScopeMarkersError,
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
    "ScopeMarkersError",
    "__version__",
    "discover_python_files",
    "format_source",
    "inspect_file",
    "process_file",
    "python_files",
)

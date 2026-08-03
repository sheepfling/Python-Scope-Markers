"""Stable programmatic API for scope-marker formatting.

This module is the supported import boundary for library users. The
implementation remains in a private module so formatting internals can evolve
without requiring callers to import private names directly. Use
``format_source`` for in-memory text, ``inspect_file`` for read-only file
inspection, ``process_file`` for checking or rewriting one file,
``strip_markers``/``strip_file`` for removal, and
``discover_python_files``/``python_files`` for discovery. Pass
``include_stubs=True`` to the discovery functions when `.pyi` files belong in
the result, or pass ``indent_width`` to formatting or file-inspection functions
to normalize logical block indentation before markers are regenerated. Use
``format_markdown_source`` and ``inspect_markdown_file`` for Python fences in
Markdown, or ``process_markdown_file`` to check or rewrite one Markdown file.
Use ``MarkerPolicy`` with ``format_source`` or the file-inspection functions
when callers need a policy other than the compatibility-preserving default.
"""

from ._implementation import (
    FileInspection,
    ScopeBoundary,
    ScopeMarkersError,
    __version__,
    discover_python_files,
    format_source,
    inspect_file,
    inspect_stripped_file,
    process_file,
    python_files,
    strip_file,
    strip_markers,
)
from ._markdown import (
    format_markdown_source,
    inspect_markdown_file,
    process_markdown_file,
)
from ._policy import (
    BoundaryKind,
    MarkerPolicy,
    PolicyError,
    classic_policy,
    describe_policy,
    expand_selectors,
    find_config,
    load_policy,
)

__all__ = (
    "BoundaryKind",
    "FileInspection",
    "MarkerPolicy",
    "PolicyError",
    "ScopeBoundary",
    "ScopeMarkersError",
    "__version__",
    "classic_policy",
    "describe_policy",
    "discover_python_files",
    "expand_selectors",
    "find_config",
    "format_markdown_source",
    "format_source",
    "inspect_file",
    "inspect_markdown_file",
    "inspect_stripped_file",
    "load_policy",
    "process_file",
    "process_markdown_file",
    "python_files",
    "strip_file",
    "strip_markers",
)

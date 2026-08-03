"""Stable programmatic API for scope-marker formatting.

Import public formatting, discovery, policy, and Markdown operations from this
module. The implementation remains private so its internals can evolve without
requiring callers to depend on private names.
"""

from ._implementation import (
    BoundaryExplanation,
    FileInspection,
    ScopeBoundary,
    ScopeMarkersError,
    __version__,
    discover_python_files,
    explain_file,
    explain_source,
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
    PolicyDecision,
    PolicyError,
    classic_policy,
    describe_policy,
    expand_selectors,
    find_config,
    load_policy,
    resolve_policy,
)

__all__ = (
    "BoundaryExplanation",
    "BoundaryKind",
    "FileInspection",
    "MarkerPolicy",
    "PolicyDecision",
    "PolicyError",
    "ScopeBoundary",
    "ScopeMarkersError",
    "__version__",
    "classic_policy",
    "describe_policy",
    "discover_python_files",
    "expand_selectors",
    "explain_file",
    "explain_source",
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
    "resolve_policy",
    "strip_file",
    "strip_markers",
)

"""Shared errors and diagnostics for file-processing operations."""

from __future__ import annotations

import tokenize
from pathlib import Path
from typing import Final, cast

from ._paths import display_path
from ._policy import PolicyError


class ScopeMarkersError(ValueError):
    """Raised when source cannot be formatted under scope-marker rules."""
####


FILE_PROCESSING_ERRORS: Final = (
    OSError,
    SyntaxError,
    UnicodeError,
    tokenize.TokenError,
    ScopeMarkersError,
    PolicyError,
)
# Keep expected input and filesystem failures consistent across public
# operations and the CLI.


def format_error(path: Path, error: BaseException) -> str:
    """Format one file-processing error with a stable source location."""
    if isinstance(error, SyntaxError):
        return (
            f"{display_path(path)}:{error.lineno or 0}:{error.offset or 0}: "
            f"{error.msg}"
        )
    ####
    if isinstance(error, tokenize.TokenError) and len(error.args) >= 2:
        message = error.args[0]
        location = error.args[1]
        if isinstance(message, str) and isinstance(location, tuple):
            location_values = cast(tuple[object, ...], location)
            if len(location_values) == 2:
                line, column = location_values
                if isinstance(line, int) and isinstance(column, int):
                    return f"{display_path(path)}:{line}:{column}: {message}"
                ####
            ####
        ####
    ####
    return f"{display_path(path)}: {error}"
####

"""Canonical project identifiers shared by repository maintenance scripts."""

from __future__ import annotations

from typing import Final

PROJECT_SLUG: Final = "scope-markers"
PACKAGE_NAME: Final = "scope_markers"


def temporary_prefix(area: str) -> str:
    """Return the standard prefix for one script's temporary directories."""
    return f"{PROJECT_SLUG}-{area}-"
####

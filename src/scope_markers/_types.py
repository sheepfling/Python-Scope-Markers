"""Shared public data types used by the package's private layers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ._policy import BoundaryKind


@dataclass(frozen=True, slots=True)
class ScopeBoundary:
    """One canonical marker insertion point."""

    index: int
    indentation: str
    indentation_width: int
    line_number: int
####


@dataclass(frozen=True, slots=True)
class BoundaryExplanation:
    """One candidate boundary and the policy decision made for it."""

    kind: BoundaryKind
    line_number: int
    insertion_line: int
    will_mark: bool
    reason: str
####


@dataclass(frozen=True, slots=True)
class FileInspection:
    """The decoded and canonical forms of one Python file."""

    path: Path
    source: str
    formatted: str
    encoding: str

    @property
    def changed(self) -> bool:
        return self.source != self.formatted
    ####
####

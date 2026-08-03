#!/usr/bin/env python3
"""Check or insert standalone ``####`` comments at Python scope boundaries."""

from __future__ import annotations

import ast
import os
import stat
import sys
import tempfile
import tokenize
from bisect import bisect_right
from collections.abc import Callable, Iterable, Iterator, Mapping, MutableSequence, Sequence
from contextlib import suppress
from dataclasses import dataclass, replace
from fnmatch import fnmatch
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from io import StringIO
from pathlib import Path
from typing import Final, cast

from ._policy import BoundaryKind, MarkerPolicy, PolicyDecision, PolicyError, classic_policy

try:
    __version__ = package_version("scope-markers")
except PackageNotFoundError:
    __version__ = "0+unknown"
####


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
# All public file operations and the CLI convert these expected input/filesystem
# failures into diagnostics. Keep the tuple shared so new operations cannot drift.


# ``####`` is the documented default; existing standalone markers can select
# ``##`` or ``####`` for compatibility with an already-formatted source tree.
MARKER: Final = "####"
MARKER_STYLES: Final = ("##", "####")
MARKDOWN_SUFFIXES: Final = frozenset({".md", ".markdown"})
# These are generated, cached, or environment-managed trees that should not
# be traversed by default. The CLI exposes --no-default-excludes when needed.
DEFAULT_SKIP_DIRECTORIES: Final = frozenset(
    {
        ".direnv",
        ".eggs",
        ".git",
        ".hg",
        ".cache",
        ".mypy_cache",
        ".nox",
        ".pyre",
        ".pytest_cache",
        ".pytype",
        ".ruff_cache",
        ".svn",
        ".tox",
        ".uv-cache",
        ".venv",
        ".vscode",
        "__pycache__",
        "__pypackages__",
        "build",
        "dist",
        "node_modules",
        "site-packages",
        "venv",
    }
)
SKIP_DIRECTORY_NAMES: Final = frozenset(name.casefold() for name in DEFAULT_SKIP_DIRECTORIES)
FUNCTION_STATEMENTS: Final = (ast.FunctionDef, ast.AsyncFunctionDef)
TRY_STATEMENTS: Final = (ast.Try, ast.TryStar)
COMPOUND_STATEMENTS: Final = (
    *FUNCTION_STATEMENTS,
    ast.ClassDef,
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.With,
    ast.AsyncWith,
    *TRY_STATEMENTS,
    ast.Match,
)

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
class _BoundaryCandidate:
    """A policy-independent analyzed marker insertion candidate."""

    kind: BoundaryKind
    boundary: ScopeBoundary
    span_lines: int
    suite_line_counts: tuple[int, ...]
    suite_statement_counts: tuple[int, ...]
    clause_count: int
    depth: int
    facts: frozenset[str]
    inline_suite: bool
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


def _first_content_row(lines: Sequence[str]) -> int | None:
    return next(
        (row for row, line in enumerate(lines, start=1) if _line_body(line).strip()),
        None,
    )
####


def _has_file_scope_opt_out(lines: Sequence[str], first_content_row: int | None) -> bool:
    """Recognize the file opt-out lexically, without tokenizing the rest of the file."""
    if first_content_row is None:
        return False
    ####
    first_content = _line_body(lines[first_content_row - 1]).strip(" \t\f").casefold()
    return first_content == "# scope-markers: off"
####


def _scope_marker_directives(lines: Sequence[str]) -> tuple[bool, frozenset[int]]:
    """Return the file opt-out and standalone ``ignore-next`` comment rows."""
    first_content_row = _first_content_row(lines)
    # A file-level opt-out must bypass tokenization: the opted-out source may
    # intentionally be incomplete or otherwise invalid Python.
    if _has_file_scope_opt_out(lines, first_content_row):
        return True, frozenset()
    ####
    ignore_next_rows: set[int] = set()
    off_rows: set[int] = set()
    for token in _token_stream("".join(lines)):
        if token.type != tokenize.COMMENT:
            continue
        ####
        row, column = token.start
        if not 1 <= row <= len(lines):
            continue
        ####
        line = _line_body(lines[row - 1])
        if line[:column].strip(" \t\f") or line[token.end[1]:].strip(" \t\f"):
            continue
        ####
        directive = token.string.strip().casefold()
        if directive == "# scope-markers: off":
            off_rows.add(row)
        elif directive == "# scope-markers: ignore-next":
            ignore_next_rows.add(row)
        ####
    ####
    return first_content_row in off_rows, frozenset(ignore_next_rows)
####


def _read_source(path: Path) -> tuple[str, str]:
    data = path.read_bytes()
    encoding, _ = tokenize.detect_encoding(_byte_line_reader(data))
    return data.decode(encoding), encoding
####


def _physical_byte_lines(data: bytes) -> Iterator[bytes]:
    """Yield byte records split only on CR, LF, and CRLF boundaries."""
    index = 0
    while index < len(data):
        start = index
        while index < len(data) and data[index] not in (ord("\r"), ord("\n")):
            index += 1
        ####
        if index == len(data):
            yield data[start:]
            return
        ####
        index += 1
        if data[index - 1] == ord("\r") and index < len(data) and data[index] == ord("\n"):
            index += 1
        ####
        yield data[start:index]
    ####
####


def _byte_line_reader(data: bytes) -> Callable[[], bytes]:
    """Return LF-normalized physical records for ``tokenize.detect_encoding``."""
    lines = iter(_physical_byte_lines(data))

    def readline() -> bytes:
        line = next(lines, b"")
        if line.endswith(b"\r\n"):
            return line[:-2] + b"\n"
        ####
        if line.endswith(b"\r"):
            return line[:-1] + b"\n"
        ####
        return line
    ####


    return readline
####


def _physical_lines(source: str) -> list[str]:
    """Split only on Python-supported CR, LF, and CRLF line boundaries."""
    return StringIO(source, newline="").readlines()
####


def _line_ending(line: str) -> str | None:
    if line.endswith("\r\n"):
        return "\r\n"
    ####
    if line.endswith("\n"):
        return "\n"
    ####
    if line.endswith("\r"):
        return "\r"
    ####
    return None
####


def _line_body(line: str) -> str:
    ending = _line_ending(line)
    if ending is None:
        return line
    ####
    return line[: -len(ending)]
####


def _preferred_newline(source: str) -> str:
    counts = {"\r\n": 0, "\n": 0, "\r": 0}
    first_seen: dict[str, int] = {}
    for index, line in enumerate(_physical_lines(source)):
        ending = _line_ending(line)
        if ending is None:
            continue
        ####
        counts[ending] += 1
        first_seen.setdefault(ending, index)
    ####
    if not any(counts.values()):
        return os.linesep
    ####
    return max(
        counts,
        key=lambda line_ending: (
            counts[line_ending],
            -first_seen.get(line_ending, sys.maxsize),
        ),
    )
####


def _newline_for_insertion(lines: Sequence[str], index: int, default: str) -> str:
    for neighbor in range(index - 1, -1, -1):
        ending = _line_ending(lines[neighbor])
        if ending is not None:
            return ending
        ####
    ####
    for neighbor in range(index, len(lines)):
        ending = _line_ending(lines[neighbor])
        if ending is not None:
            return ending
        ####
    ####
    return default
####


def _indentation_prefix(line: str) -> str:
    index = 0
    while index < len(line) and line[index] in " \t\f":
        index += 1
    ####
    return line[:index]
####


def _indentation_width(indentation: str) -> int:
    """Return Python's visual indentation width for spaces, tabs, and form-feed characters."""
    width = 0
    for character in indentation:
        if character == " ":
            width += 1
        elif character == "\t":
            width = (width // 8 + 1) * 8
        elif character == "\f":
            width = 0
        ####
    ####
    return width
####


def _token_stream(source: str) -> Iterable[tokenize.TokenInfo]:
    """Tokenize source using LF records while preserving physical source rows."""
    lines = iter(_physical_lines(source))

    def readline() -> str:
        line = next(lines, "")
        ending = _line_ending(line)
        if ending is None:
            return line
        ####
        return f"{line[: -len(ending)]}\n"
    ####


    return tokenize.generate_tokens(readline)
####


def _marker_lines_from_tokens(
        tokens: Iterable[tokenize.TokenInfo], lines: Sequence[str], marker: str
) -> set[int]:
    marker_lines: set[int] = set()
    for token in tokens:
        if token.type != tokenize.COMMENT or token.string.rstrip(" \t\f") != marker:
            continue
        ####
        row = token.start[0]
        if 1 <= row <= len(lines) and _line_body(lines[row - 1]).strip(" \t\f") == marker:
            marker_lines.add(row - 1)
        ####
    ####
    return marker_lines
####


def _indentation_safe_source(source: str) -> str:
    """Make indentation recoverable for lexical comment scanning."""
    levels = [0]
    normalized: list[str] = []
    for line in _physical_lines(source):
        body = _line_body(line)
        prefix_length = len(body) - len(body.lstrip(" \t\f"))
        if not body.strip(" \t\f"):
            normalized.append(line)
            continue
        ####
        width = _indentation_width(body[:prefix_length])
        if width > levels[-1]:
            levels.append(width)
        elif width in levels:
            levels = levels[: levels.index(width) + 1]
        else:
            width = max(level for level in levels if level < width)
            levels = levels[: levels.index(width) + 1]
        ####
        ending = _line_ending(line) or ""
        normalized.append(" " * width + body[prefix_length:] + ending)
    ####
    return "".join(normalized)
####


def _standalone_marker_lines(source: str, marker: str) -> set[int]:
    lines = _physical_lines(source)
    try:
        return _marker_lines_from_tokens(_token_stream(source), lines, marker)
    except IndentationError:
        return _marker_lines_from_tokens(
            _token_stream(_indentation_safe_source(source)), lines, marker
        )
    ####
####


def _detect_marker_style(source: str) -> str:
    styles = {marker for marker in MARKER_STYLES if _standalone_marker_lines(source, marker)}
    if len(styles) > 1:
        found = ", ".join(sorted(styles))
        raise ScopeMarkersError(
            f"conflicting standalone marker styles: {found}; "
            "keep one marker style per file or remove the conflicting markers"
        )
    ####
    return next(iter(styles), MARKER)
####


def _without_markers(source: str, marker: str) -> str:
    marker_lines = _standalone_marker_lines(source, marker)
    if not marker_lines:
        return source
    ####
    lines = _physical_lines(source)
    return "".join(line for index, line in enumerate(lines) if index not in marker_lines)
####


def strip_markers(source: str) -> str:
    """Remove every standalone recognized scope-marker comment from source."""
    marker_lines: set[int] = set()
    for marker in MARKER_STYLES:
        marker_lines.update(_standalone_marker_lines(source, marker))
    ####
    if not marker_lines:
        return source
    ####
    lines = _physical_lines(source)
    return "".join(line for index, line in enumerate(lines) if index not in marker_lines)
####


def _parents(tree: ast.AST) -> dict[int, ast.AST]:
    parents: dict[int, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[id(child)] = parent
        ####
    ####
    return parents
####


def _header_indentation_width(node: ast.stmt, lines: Sequence[str]) -> int | None:
    """Return a header's effective Python indentation when it is available."""
    if not 1 <= node.lineno <= len(lines):
        return None
    ####
    return _indentation_width(_indentation_prefix(lines[node.lineno - 1]))
####


def _is_elif(
        node: ast.If, parents: Mapping[int, ast.AST], lines: Sequence[str]
) -> bool:
    parent = parents.get(id(node))
    parent_width = (
        _header_indentation_width(parent, lines) if isinstance(parent, ast.If) else None
    )
    node_width = _header_indentation_width(node, lines)
    return (
            isinstance(parent, ast.If)
            and bool(parent.orelse)
            and parent.orelse[0] is node
            and parent_width is not None
            and parent_width == node_width
    )
####


def _next_elif(
        node: ast.If, parents: Mapping[int, ast.AST], lines: Sequence[str]
) -> ast.If | None:
    if len(node.orelse) != 1:
        return None
    ####
    candidate = node.orelse[0]
    if isinstance(candidate, ast.If) and _is_elif(candidate, parents, lines):
        return candidate
    ####
    return None
####


def _is_stub_function(node: ast.stmt) -> bool:
    if not isinstance(node, FUNCTION_STATEMENTS) or not node.body:
        return False
    ####
    return all(
        isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Constant)
        and (isinstance(statement.value.value, str) or statement.value.value is Ellipsis)
        for statement in node.body
    )
####


def _compound_nodes(tree: ast.AST, lines: Sequence[str]) -> list[ast.stmt]:
    parents = _parents(tree)
    nodes: list[ast.stmt] = []
    for candidate in ast.walk(tree):
        if not isinstance(candidate, ast.stmt) or not isinstance(candidate, COMPOUND_STATEMENTS):
            continue
        ####
        node = candidate
        if isinstance(node, ast.If) and _is_elif(node, parents, lines):
            continue
        ####
        nodes.append(node)
    ####
    return nodes
####


def _insertion_index(lines: Sequence[str], node: ast.stmt, indentation_width: int) -> int:
    if node.end_lineno is None:
        raise ScopeMarkersError(
            f"{type(node).__name__} at line {node.lineno} has no end location"
        )
    ####
    for index in range(node.end_lineno, len(lines)):
        line = lines[index]
        if not _line_body(line).strip(" \t\f"):
            return index
        ####
        following_width = _indentation_width(_indentation_prefix(line))
        if following_width <= indentation_width:
            return index
        ####
    ####
    return len(lines)
####


def _match_case_header_lines(lines: Sequence[str]) -> list[int]:
    case_lines: list[int] = []
    at_statement_start = True
    source = "".join(lines)
    for token in _token_stream(source):
        if token.type == tokenize.NAME and token.string == "case" and at_statement_start:
            case_lines.append(token.start[0])
        ####
        # NL and backslash continuations stay in the same logical statement;
        # only NEWLINE can begin another clause header.
        if token.type == tokenize.NEWLINE:
            at_statement_start = True
        elif token.type not in (
                tokenize.INDENT,
                tokenize.DEDENT,
                tokenize.COMMENT,
                tokenize.NL,
        ):
            at_statement_start = False
        ####
    ####
    return case_lines
####


def _clause_header_lines(lines: Sequence[str]) -> Mapping[str, list[int]]:
    """Index clause keywords at tokenizer-recognized statement starts."""
    headers: dict[str, list[int]] = {
        keyword: [] for keyword in ("else", "except", "finally")
    }
    at_statement_start = True
    for token in _token_stream("".join(lines)):
        if (
                token.type == tokenize.NAME
                and token.string in headers
                and at_statement_start
        ):
            headers[token.string].append(token.start[0])
        ####
        if token.type == tokenize.NEWLINE:
            at_statement_start = True
        elif token.type not in (
                tokenize.INDENT,
                tokenize.DEDENT,
                tokenize.COMMENT,
                tokenize.NL,
        ):
            at_statement_start = False
        ####
    ####
    return headers
####


def _match_case_line_number(case_header_lines: Sequence[int], pattern_line: int) -> int:
    header_index = bisect_right(case_header_lines, pattern_line) - 1
    if header_index >= 0:
        return case_header_lines[header_index]
    ####
    raise ScopeMarkersError("match case has no case header")
####


def _match_case_boundary(
        case: ast.match_case,
        lines: Sequence[str],
        case_header_lines: Sequence[int],
) -> ScopeBoundary | None:
    if not case.body:
        return None
    ####
    pattern_line = getattr(case.pattern, "lineno", None)
    if not isinstance(pattern_line, int) or not 1 <= pattern_line <= len(lines):
        raise ScopeMarkersError("match case has an invalid source location")
    ####
    line_number = _match_case_line_number(case_header_lines, pattern_line)
    indentation = _indentation_prefix(lines[line_number - 1])
    width = _indentation_width(indentation)
    return ScopeBoundary(
        index=_insertion_index(lines, case.body[-1], width),
        indentation=indentation,
        indentation_width=width,
        line_number=line_number,
    )
####


def _compound_boundary(node: ast.stmt, lines: Sequence[str]) -> ScopeBoundary:
    if not 1 <= node.lineno <= len(lines):
        raise ScopeMarkersError("compound statement has an invalid source location")
    ####
    indentation = _indentation_prefix(lines[node.lineno - 1])
    width = _indentation_width(indentation)
    return ScopeBoundary(
        index=_insertion_index(lines, node, width),
        indentation=indentation,
        indentation_width=width,
        line_number=node.lineno,
    )
####


def _scope_boundaries(
        tree: ast.AST,
        lines: Sequence[str],
        *,
        policy: MarkerPolicy,
) -> list[ScopeBoundary]:
    boundaries: list[ScopeBoundary] = []
    seen: set[tuple[int, str]] = set()
    candidates = _boundary_candidates(tree, lines)
    ignored = _ignored_candidate_identities(candidates, lines, policy)
    for candidate in candidates:
        identity = (candidate.boundary.index, candidate.boundary.indentation)
        if identity in ignored or not _candidate_decision(candidate, policy).allowed:
            continue
        ####
        if identity not in seen:
            seen.add(identity)
            boundaries.append(candidate.boundary)
        ####
    ####
    return boundaries
####


def _ignored_candidate_identities(
        candidates: Sequence[_BoundaryCandidate],
        lines: Sequence[str],
        policy: MarkerPolicy,
) -> set[tuple[int, str]]:
    _, ignore_next_rows = _scope_marker_directives(lines)
    if not ignore_next_rows:
        return set()
    ####
    selected = sorted(
        (
            candidate
            for candidate in candidates
            if _candidate_decision(candidate, policy).allowed
        ),
        key=lambda candidate: (
            candidate.boundary.line_number,
            candidate.boundary.index,
            str(candidate.kind),
        ),
    )
    ignored: set[tuple[int, str]] = set()
    for row in sorted(ignore_next_rows):
        target = next(
            (
                candidate
                for candidate in selected
                if candidate.boundary.line_number > row
            ),
            None,
        )
        if target is not None:
            ignored.add((target.boundary.index, target.boundary.indentation))
        ####
    ####
    return ignored
####


def _boundary_candidates(tree: ast.AST, lines: Sequence[str]) -> list[_BoundaryCandidate]:
    parents = _parents(tree)
    nodes = _compound_nodes(tree, lines)
    case_header_lines = _match_case_header_lines(lines)
    clause_header_lines = _clause_header_lines(lines)
    inline_headers = _inline_suite_header_lines(
        "".join(lines),
        _compound_header_lines(tree, lines)
        | set(case_header_lines)
        | {line for headers in clause_header_lines.values() for line in headers},
    )
    candidates = [
        _compound_candidate(node, lines, parents, inline_headers)
        for node in nodes
    ]
    for node in nodes:
        candidates.extend(
            _clause_candidates(
                node,
                lines,
                parents,
                clause_header_lines,
                inline_headers,
            )
        )
    ####
    for match in (node for node in nodes if isinstance(node, ast.Match)):
        match_depth = _candidate_depth(match, parents)
        case_facts = _candidate_facts(match, parents, lines, match_depth + 1)
        for case in match.cases:
            candidate = _case_candidate(
                case,
                lines,
                case_header_lines,
                inline_headers,
                match_depth + 1,
                case_facts,
            )
            if candidate is not None:
                candidates.append(candidate)
            ####
        ####
    ####
    return candidates
####


def _candidate_decision(
        candidate: _BoundaryCandidate, policy: MarkerPolicy
) -> PolicyDecision:
    return policy.decision(
        candidate.kind,
        span_lines=candidate.span_lines,
        suite_line_counts=candidate.suite_line_counts,
        suite_statement_counts=candidate.suite_statement_counts,
        clause_count=candidate.clause_count,
        depth=candidate.depth,
        facts=candidate.facts,
        inline_suite=candidate.inline_suite,
    )
####


def _ast_equivalent(left: ast.AST, right: ast.AST) -> bool:
    """Compare AST structure iteratively, excluding source-location attributes."""
    pending: list[tuple[object, object]] = [(left, right)]
    while pending:
        current_left, current_right = pending.pop()
        if isinstance(current_left, ast.AST):
            if not isinstance(current_right, ast.AST):
                return False
            ####
            if type(current_left) is not type(current_right):
                return False
            ####
            for field in reversed(current_left._fields):
                pending.append((getattr(current_left, field), getattr(current_right, field)))
            ####
            continue
        ####
        if isinstance(current_left, list):
            if not isinstance(current_right, list):
                return False
            ####
            left_items = cast(list[object], current_left)
            right_items = cast(list[object], current_right)
            if len(left_items) != len(right_items):
                return False
            ####
            pending.extend(zip(reversed(left_items), reversed(right_items), strict=True))
            continue
        ####
        if current_left != current_right:
            return False
        ####
    ####
    return True
####


def _block_indentation_depths(lines: Sequence[str], source: str) -> dict[str, int]:
    """Map source indentation prefixes to their tokenizer-recognized depths."""
    depths = {"": 0}
    depth = 0
    for token in _token_stream(source):
        if token.type == tokenize.INDENT:
            depth += 1
            row = token.start[0]
            if 1 <= row <= len(lines):
                depths[_indentation_prefix(lines[row - 1])] = depth
            ####
        elif token.type == tokenize.DEDENT:
            depth -= 1
        ####
    ####
    return depths
####


def _logical_statement_depths(source: str) -> dict[int, int]:
    """Return tokenizer-recognized block depth for each logical statement line."""
    depths: dict[int, int] = {}
    depth = 0
    at_statement_start = True
    for token in _token_stream(source):
        if token.type == tokenize.INDENT:
            depth += 1
            continue
        ####
        if token.type == tokenize.DEDENT:
            depth -= 1
            continue
        ####
        if token.type == tokenize.NEWLINE:
            at_statement_start = True
            continue
        ####
        if token.type in (tokenize.COMMENT, tokenize.NL, tokenize.ENDMARKER):
            continue
        ####
        if at_statement_start:
            depths[token.start[0]] = depth
        ####
        at_statement_start = False
    ####
    return depths
####


def _compound_header_lines(tree: ast.AST, lines: Sequence[str]) -> set[int]:
    """Return physical lines that begin compound statements or clauses."""
    headers = {
        candidate.lineno
        for candidate in ast.walk(tree)
        if isinstance(candidate, ast.stmt) and isinstance(candidate, COMPOUND_STATEMENTS)
    }
    headers.update(_match_case_header_lines(lines))
    at_statement_start = True
    for token in _token_stream("".join(lines)):
        if (
                token.type == tokenize.NAME
                and token.string in {"else", "except", "finally"}
                and at_statement_start
        ):
            headers.add(token.start[0])
        ####
        if token.type == tokenize.NEWLINE:
            at_statement_start = True
        elif token.type not in (
                tokenize.INDENT,
                tokenize.DEDENT,
                tokenize.COMMENT,
                tokenize.NL,
        ):
            at_statement_start = False
        ####
    ####
    return headers
####


def _inline_suite_header_lines(source: str, header_lines: set[int]) -> set[int]:
    """Return headers whose suite continues on the same physical line."""
    inline_headers: set[int] = set()
    ignored = {tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.ENDMARKER}
    opening = {"(", "[", "{"}
    closing = {
        ")": "(",
        "]": "[",
        "}": "{",
    }
    active_row: int | None = None
    bracket_stack: list[str] = []
    colon_row: int | None = None
    for token in _token_stream(source):
        if active_row is None:
            if token.start[0] in header_lines:
                active_row = token.start[0]
            else:
                continue
            ####
        ####
        if token.type == tokenize.NEWLINE:
            active_row = None
            bracket_stack.clear()
            colon_row = None
            continue
        ####
        if colon_row is None:
            if token.type == tokenize.OP and token.string in opening:
                bracket_stack.append(token.string)
                continue
            ####
            if token.type == tokenize.OP and token.string in closing:
                if bracket_stack and bracket_stack[-1] == closing[token.string]:
                    bracket_stack.pop()
                ####
                continue
            ####
            if (
                    token.type == tokenize.OP
                    and token.string == ":"
                    and not bracket_stack
            ):
                colon_row = token.start[0]
            ####
            continue
        ####
        if token.type not in ignored:
            inline_headers.add(colon_row)
            active_row = None
            bracket_stack.clear()
            colon_row = None
        ####
    ####
    return inline_headers
####


def _inline_suite_comment_depths(
        tree: ast.AST, lines: Sequence[str], statement_depths: Mapping[int, int]
) -> dict[int, int]:
    """Infer virtual child depth for comments after inline compound suites."""
    comments: dict[int, int] = {}
    source = "".join(lines)
    headers = _inline_suite_header_lines(source, _compound_header_lines(tree, lines))
    for row in headers:
        depth = statement_depths.get(row)
        if depth is None:
            preceding_rows = [candidate for candidate in statement_depths if candidate < row]
            if preceding_rows:
                depth = statement_depths[max(preceding_rows)]
            ####
        ####
        if depth is None:
            continue
        ####
        header_width = _indentation_width(_indentation_prefix(lines[row - 1]))
        for comment_row in range(row + 1, len(lines) + 1):
            line = _line_body(lines[comment_row - 1])
            if not line.strip(" \t\f"):
                continue
            ####
            prefix = _indentation_prefix(line)
            if not line[len(prefix):].startswith("#"):
                break
            ####
            if _indentation_width(prefix) > header_width:
                comments[comment_row] = depth + 1
            ####
        ####
    ####
    return comments
####


def _replace_indentation(line: str, indentation: str) -> str:
    prefix = _indentation_prefix(line)
    return f"{indentation}{line[len(prefix):]}"
####


def _reindent_source(source: str, indent_width: int) -> str:
    """Normalize logical block indentation while retaining continuation alignment."""
    if indent_width < 1:
        raise ScopeMarkersError("indent_width must be a positive integer")
    ####
    original_tree = ast.parse(source)
    lines = _physical_lines(source)
    prefix_depths = _block_indentation_depths(lines, source)
    inline_comment_depths = _inline_suite_comment_depths(
        original_tree, lines, _logical_statement_depths(source)
    )
    depth = 0
    at_statement_start = True
    for token in _token_stream(source):
        if token.type == tokenize.INDENT:
            depth += 1
            continue
        ####
        if token.type == tokenize.DEDENT:
            depth -= 1
            continue
        ####
        if token.type == tokenize.NEWLINE:
            at_statement_start = True
            continue
        ####
        if token.type == tokenize.COMMENT and at_statement_start:
            row = token.start[0]
            if 1 <= row <= len(lines):
                prefix = _indentation_prefix(lines[row - 1])
                comment_depth = inline_comment_depths.get(row, prefix_depths.get(prefix))
                if comment_depth is not None:
                    lines[row - 1] = _replace_indentation(
                        lines[row - 1], " " * (indent_width * comment_depth)
                    )
                ####
            ####
            continue
        ####
        if token.type in (tokenize.NL, tokenize.ENDMARKER):
            continue
        ####
        if at_statement_start:
            row = token.start[0]
            if 1 <= row <= len(lines):
                lines[row - 1] = _replace_indentation(
                    lines[row - 1], " " * (indent_width * depth)
                )
            ####
        ####
        at_statement_start = False
    ####
    reindented = "".join(lines)
    if not _ast_equivalent(ast.parse(reindented), original_tree):
        raise ScopeMarkersError("indentation normalization changed the Python AST")
    ####
    return reindented
####


def format_source(
        source: str,
        *,
        filename: str = "<unknown>",
        mark_stubs: bool = False,
        indent_width: int | None = None,
        policy: MarkerPolicy | None = None,
) -> str:
    """Return source with canonical markers after supported compound statements."""
    if _scope_marker_directives(_physical_lines(source))[0]:
        return source
    ####
    source, clean_source, tree, lines, marker, effective_policy = _prepare_source(
        source,
        filename=filename,
        mark_stubs=mark_stubs,
        indent_width=indent_width,
        policy=policy,
    )
    default_newline = _preferred_newline(clean_source or source)
    insertions: dict[int, list[ScopeBoundary]] = {}
    for boundary in _scope_boundaries(tree, lines, policy=effective_policy):
        insertions.setdefault(boundary.index, []).append(boundary)
    ####
    for index in sorted(insertions, reverse=True):
        newline = _newline_for_insertion(lines, index, default_newline)
        if index > 0 and _line_ending(lines[index - 1]) is None:
            lines[index - 1] += newline
        ####
        ordered = sorted(
            insertions[index],
            key=lambda candidate: (candidate.indentation_width, candidate.line_number),
            reverse=True,
        )
        markers = [f"{boundary.indentation}{marker}{newline}" for boundary in ordered]
        lines[index:index] = markers
    ####
    formatted = "".join(lines)
    formatted_tree = ast.parse(formatted, filename=filename)
    if not _ast_equivalent(formatted_tree, tree):
        raise ScopeMarkersError("scope-marker formatting changed the Python AST")
    ####
    return formatted
####


def explain_source(
        source: str,
        *,
        filename: str = "<unknown>",
        mark_stubs: bool = False,
        indent_width: int | None = None,
        policy: MarkerPolicy | None = None,
) -> tuple[BoundaryExplanation, ...]:
    """Explain every candidate boundary for an in-memory Python source string."""
    if _scope_marker_directives(_physical_lines(source))[0]:
        return ()
    ####
    _, _, tree, lines, _, effective_policy = _prepare_source(
        source,
        filename=filename,
        mark_stubs=mark_stubs,
        indent_width=indent_width,
        policy=policy,
    )
    explanations: list[BoundaryExplanation] = []
    selected: dict[tuple[int, str], BoundaryKind] = {}
    candidates = _boundary_candidates(tree, lines)
    ignored = _ignored_candidate_identities(candidates, lines, effective_policy)
    for candidate in candidates:
        decision = _candidate_decision(candidate, effective_policy)
        identity = (candidate.boundary.index, candidate.boundary.indentation)
        if identity in ignored:
            decision = PolicyDecision(False, "ignored by source directive")
        ####
        will_mark = decision.allowed and identity not in selected
        reason = decision.reason
        if decision.allowed and not will_mark:
            reason = f"duplicates selected {selected[identity]} boundary"
        elif will_mark:
            selected[identity] = candidate.kind
        ####
        explanations.append(
            BoundaryExplanation(
                kind=candidate.kind,
                line_number=candidate.boundary.line_number,
                insertion_line=candidate.boundary.index + 1,
                will_mark=will_mark,
                reason=reason,
            )
        )
    ####
    return tuple(explanations)
####


def _prepare_source(
        source: str,
        *,
        filename: str,
        mark_stubs: bool,
        indent_width: int | None,
        policy: MarkerPolicy | None,
) -> tuple[str, str, ast.AST, list[str], str, MarkerPolicy]:
    if indent_width is not None:
        source = _reindent_source(source, indent_width)
    ####
    marker = _detect_marker_style(source)
    clean_source = _without_markers(source, marker)
    tree = ast.parse(clean_source, filename=filename)
    lines = _physical_lines(clean_source)
    effective_policy = policy or classic_policy(mark_stubs=mark_stubs)
    if mark_stubs and policy is not None and policy.stub_policy == "skip":
        effective_policy = replace(policy, stub_policy="mark")
    ####
    return source, clean_source, tree, lines, marker, effective_policy
####


def _matches_pattern(path: Path, root: Path, patterns: tuple[str, ...]) -> bool:
    relative = path.relative_to(root).as_posix()
    absolute = path.absolute().as_posix()
    resolved = path.resolve(strict=False).as_posix()
    return any(
        fnmatch(path.name, pattern)
        or fnmatch(relative, pattern)
        or fnmatch(absolute, pattern)
        or fnmatch(resolved, pattern)
        for pattern in patterns
    )
####


def _is_generated_root(path: Path, use_default_excludes: bool) -> bool:
    return use_default_excludes and any(
        _is_skipped_directory(part) for part in path.resolve().parts
    )
####


def _is_skipped_directory(name: str) -> bool:
    normalized = name.casefold()
    return normalized in SKIP_DIRECTORY_NAMES or normalized.endswith(".egg-info")
####


def _is_excluded_path(path: Path, root: Path, patterns: tuple[str, ...]) -> bool:
    return _matches_pattern(path, root, patterns)
####


def _should_prune_directory(
        name: str,
        path: Path,
        root: Path,
        patterns: tuple[str, ...],
        use_default_excludes: bool,
) -> bool:
    # Prune before descent: generated/default-excluded trees and symlinked or
    # explicitly excluded directories must never enter recursive discovery.
    return (
            (use_default_excludes and _is_skipped_directory(name))
            or path.is_symlink()
            or _is_excluded_path(path, root, patterns)
    )
####


def _is_supported_source_file(
        path: Path,
        root: Path,
        include_patterns: tuple[str, ...],
        include_stubs: bool,
        include_markdown: bool,
) -> bool:
    return (
            path.suffix.casefold() == ".py"
            or (include_stubs and path.suffix.casefold() == ".pyi")
            or (include_markdown and path.suffix.casefold() in MARKDOWN_SUFFIXES)
            or (
                    path.suffix.casefold() not in MARKDOWN_SUFFIXES
                    and _matches_pattern(path, root, include_patterns)
            )
    )
####


def _clause_boundary(
        suite: Sequence[ast.stmt], lines: Sequence[str], header_line: int
) -> ScopeBoundary:
    if not suite or not 1 <= header_line <= len(lines):
        raise ScopeMarkersError("compound clause has an invalid source location")
    ####
    indentation = _indentation_prefix(lines[header_line - 1])
    width = _indentation_width(indentation)
    return ScopeBoundary(
        index=_insertion_index(lines, suite[-1], width),
        indentation=indentation,
        indentation_width=width,
        line_number=header_line,
    )
####


def _compound_kind(node: ast.stmt) -> BoundaryKind:
    if isinstance(node, FUNCTION_STATEMENTS):
        return BoundaryKind.STATEMENT_FUNCTION
    ####
    if isinstance(node, ast.ClassDef):
        return BoundaryKind.STATEMENT_CLASS
    ####
    if isinstance(node, ast.If):
        return BoundaryKind.STATEMENT_IF
    ####
    if isinstance(node, (ast.For, ast.AsyncFor)):
        return BoundaryKind.STATEMENT_FOR
    ####
    if isinstance(node, ast.While):
        return BoundaryKind.STATEMENT_WHILE
    ####
    if isinstance(node, (ast.With, ast.AsyncWith)):
        return BoundaryKind.STATEMENT_WITH
    ####
    if isinstance(node, TRY_STATEMENTS):
        return BoundaryKind.STATEMENT_TRY
    ####
    if isinstance(node, ast.Match):
        return BoundaryKind.STATEMENT_MATCH
    ####
    raise ScopeMarkersError(f"unsupported compound statement: {type(node).__name__}")
####


def _if_suites(
        node: ast.If, parents: Mapping[int, ast.AST], lines: Sequence[str]
) -> tuple[Sequence[ast.stmt], ...]:
    suites: list[Sequence[ast.stmt]] = [node.body]
    current = node
    while (next_elif := _next_elif(current, parents, lines)) is not None:
        current = next_elif
        suites.append(current.body)
    ####
    if current.orelse:
        suites.append(current.orelse)
    ####
    return tuple(suites)
####


def _owned_suites(
        node: ast.stmt, parents: Mapping[int, ast.AST], lines: Sequence[str]
) -> tuple[Sequence[ast.stmt], ...]:
    if isinstance(node, ast.If):
        return _if_suites(node, parents, lines)
    ####
    if isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
        return tuple(suite for suite in (node.body, node.orelse) if suite)
    ####
    if isinstance(node, TRY_STATEMENTS):
        return tuple(
            suite
            for suite in (
                node.body,
                *(handler.body for handler in node.handlers),
                node.orelse,
                node.finalbody,
            )
            if suite
        )
    ####
    if isinstance(node, ast.Match):
        return tuple(case.body for case in node.cases if case.body)
    ####
    body = getattr(node, "body", ())
    return (body,) if body else ()
####


def _suite_line_count(suite: Sequence[ast.stmt]) -> int:
    if not suite:
        return 0
    ####
    start = suite[0].lineno
    end = suite[-1].end_lineno
    return max(1, (end if end is not None else start) - start + 1)
####


def _ancestor_nodes(node: ast.AST, parents: Mapping[int, ast.AST]) -> Iterator[ast.AST]:
    parent = parents.get(id(node))
    while parent is not None:
        yield parent
        parent = parents.get(id(parent))
    ####
####


def _candidate_depth(node: ast.AST, parents: Mapping[int, ast.AST]) -> int:
    return sum(
        isinstance(parent, COMPOUND_STATEMENTS) for parent in _ancestor_nodes(node, parents)
    )
####


def _candidate_facts(
        node: ast.stmt,
        parents: Mapping[int, ast.AST],
        lines: Sequence[str],
        depth: int,
) -> frozenset[str]:
    facts: set[str] = set()
    ancestors = tuple(_ancestor_nodes(node, parents))
    if isinstance(parents.get(id(node)), ast.Module):
        facts.add("module-level")
    ####
    if any(isinstance(ancestor, ast.ClassDef) for ancestor in ancestors):
        facts.add("class-level")
    ####
    if any(isinstance(ancestor, FUNCTION_STATEMENTS) for ancestor in ancestors):
        facts.add("function-level")
    ####
    if depth:
        facts.add("nested")
    ####
    if _is_stub_function(node):
        facts.add("stub")
    ####
    if isinstance(node, ast.If):
        current = node
        has_elif = False
        while (next_elif := _next_elif(current, parents, lines)) is not None:
            has_elif = True
            current = next_elif
        ####
        if has_elif:
            facts.add("has-elif")
        ####
        if current.orelse:
            facts.add("has-else")
        ####
    elif isinstance(node, TRY_STATEMENTS):
        if len(node.handlers) > 1:
            facts.add("multiple-handlers")
        ####
        if node.finalbody:
            facts.add("has-finally")
        ####
    elif isinstance(node, ast.Match) and len(node.cases) > 1:
        facts.add("multiple-cases")
    ####
    return frozenset(facts)
####


def _compound_candidate(
        node: ast.stmt,
        lines: Sequence[str],
        parents: Mapping[int, ast.AST],
        inline_headers: set[int],
) -> _BoundaryCandidate:
    suites = _owned_suites(node, parents, lines)
    boundary = _compound_boundary(node, lines)
    end_line = node.end_lineno if node.end_lineno is not None else node.lineno
    depth = _candidate_depth(node, parents)
    return _BoundaryCandidate(
        kind=_compound_kind(node),
        boundary=boundary,
        span_lines=max(1, end_line - node.lineno + 1),
        suite_line_counts=tuple(_suite_line_count(suite) for suite in suites),
        suite_statement_counts=tuple(len(suite) for suite in suites),
        clause_count=len(suites),
        depth=depth,
        facts=_candidate_facts(node, parents, lines, depth),
        inline_suite=any(
            suite and suite[0].lineno in inline_headers for suite in suites
        ),
    )
####


def _case_candidate(
        case: ast.match_case,
        lines: Sequence[str],
        case_header_lines: Sequence[int],
        inline_headers: set[int],
        depth: int,
        facts: frozenset[str],
) -> _BoundaryCandidate | None:
    boundary = _match_case_boundary(case, lines, case_header_lines)
    if boundary is None or not case.body:
        return None
    ####
    end_line = case.body[-1].end_lineno or case.body[-1].lineno
    return _BoundaryCandidate(
        kind=BoundaryKind.CLAUSE_MATCH_CASE,
        boundary=boundary,
        span_lines=max(1, end_line - boundary.line_number + 1),
        suite_line_counts=(_suite_line_count(case.body),),
        suite_statement_counts=(len(case.body),),
        clause_count=1,
        depth=depth,
        facts=facts,
        inline_suite=case.body[0].lineno in inline_headers,
    )
####


def _clause_header_line(
        keyword: str,
        suite: Sequence[ast.stmt],
        owner: ast.stmt,
        lines: Sequence[str],
        headers: Mapping[str, Sequence[int]],
) -> int:
    if not suite:
        raise ScopeMarkersError(f"{keyword} clause has no body")
    ####
    owner_width = _header_indentation_width(owner, lines)
    if owner_width is None:
        raise ScopeMarkersError(f"{keyword} clause has an invalid source location")
    ####
    for line_number in reversed(headers[keyword]):
        if line_number < owner.lineno:
            break
        ####
        if line_number > suite[0].lineno:
            continue
        ####
        if _indentation_width(_indentation_prefix(lines[line_number - 1])) == owner_width:
            return line_number
        ####
    ####
    raise ScopeMarkersError(f"{keyword} clause has no header")
####


def _clause_candidate(
        kind: BoundaryKind,
        suite: Sequence[ast.stmt],
        lines: Sequence[str],
        header_line: int,
        depth: int,
        facts: frozenset[str],
        inline_headers: set[int],
) -> _BoundaryCandidate:
    boundary = _clause_boundary(suite, lines, header_line)
    end_line = suite[-1].end_lineno or suite[-1].lineno
    return _BoundaryCandidate(
        kind=kind,
        boundary=boundary,
        span_lines=max(1, end_line - header_line + 1),
        suite_line_counts=(_suite_line_count(suite),),
        suite_statement_counts=(len(suite),),
        clause_count=1,
        depth=depth,
        facts=facts,
        inline_suite=suite[0].lineno in inline_headers,
    )
####


def _if_clause_candidates(
        node: ast.If,
        lines: Sequence[str],
        parents: Mapping[int, ast.AST],
        headers: Mapping[str, Sequence[int]],
        inline_headers: set[int],
) -> list[_BoundaryCandidate]:
    depth = _candidate_depth(node, parents) + 1
    facts = _candidate_facts(node, parents, lines, depth)
    candidates = [
        _clause_candidate(
            BoundaryKind.CLAUSE_IF_BODY,
            node.body,
            lines,
            node.lineno,
            depth,
            facts,
            inline_headers,
        )
    ]
    current = node
    while (next_elif := _next_elif(current, parents, lines)) is not None:
        current = next_elif
        candidates.append(
            _clause_candidate(
                BoundaryKind.CLAUSE_IF_ELIF,
                current.body,
                lines,
                current.lineno,
                depth,
                facts,
                inline_headers,
            )
        )
    ####
    if current.orelse:
        candidates.append(
            _clause_candidate(
                BoundaryKind.CLAUSE_IF_ELSE,
                current.orelse,
                lines,
                _clause_header_line("else", current.orelse, node, lines, headers),
                depth,
                facts,
                inline_headers,
            )
        )
    ####
    return candidates
####


def _loop_clause_candidates(
        node: ast.For | ast.AsyncFor | ast.While,
        lines: Sequence[str],
        parents: Mapping[int, ast.AST],
        headers: Mapping[str, Sequence[int]],
        inline_headers: set[int],
) -> list[_BoundaryCandidate]:
    depth = _candidate_depth(node, parents) + 1
    facts = _candidate_facts(node, parents, lines, depth)
    body_kind, else_kind = (
        (BoundaryKind.CLAUSE_FOR_BODY, BoundaryKind.CLAUSE_FOR_ELSE)
        if isinstance(node, (ast.For, ast.AsyncFor))
        else (BoundaryKind.CLAUSE_WHILE_BODY, BoundaryKind.CLAUSE_WHILE_ELSE)
    )
    candidates = [
        _clause_candidate(
            body_kind,
            node.body,
            lines,
            node.lineno,
            depth,
            facts,
            inline_headers,
        )
    ]
    if node.orelse:
        candidates.append(
            _clause_candidate(
                else_kind,
                node.orelse,
                lines,
                _clause_header_line("else", node.orelse, node, lines, headers),
                depth,
                facts,
                inline_headers,
            )
        )
    ####
    return candidates
####


def _try_clause_candidates(
        node: ast.Try | ast.TryStar,
        lines: Sequence[str],
        parents: Mapping[int, ast.AST],
        headers: Mapping[str, Sequence[int]],
        inline_headers: set[int],
) -> list[_BoundaryCandidate]:
    depth = _candidate_depth(node, parents) + 1
    facts = _candidate_facts(node, parents, lines, depth)
    candidates = [
        _clause_candidate(
            BoundaryKind.CLAUSE_TRY_BODY,
            node.body,
            lines,
            node.lineno,
            depth,
            facts,
            inline_headers,
        )
    ]
    for handler in node.handlers:
        candidates.append(
            _clause_candidate(
                BoundaryKind.CLAUSE_TRY_EXCEPT,
                handler.body,
                lines,
                _clause_header_line("except", handler.body, node, lines, headers),
                depth,
                facts,
                inline_headers,
            )
        )
    ####
    if node.orelse:
        candidates.append(
            _clause_candidate(
                BoundaryKind.CLAUSE_TRY_ELSE,
                node.orelse,
                lines,
                _clause_header_line("else", node.orelse, node, lines, headers),
                depth,
                facts,
                inline_headers,
            )
        )
    ####
    if node.finalbody:
        candidates.append(
            _clause_candidate(
                BoundaryKind.CLAUSE_TRY_FINALLY,
                node.finalbody,
                lines,
                _clause_header_line("finally", node.finalbody, node, lines, headers),
                depth,
                facts,
                inline_headers,
            )
        )
    ####
    return candidates
####


def _clause_candidates(
        node: ast.stmt,
        lines: Sequence[str],
        parents: Mapping[int, ast.AST],
        headers: Mapping[str, Sequence[int]],
        inline_headers: set[int],
) -> list[_BoundaryCandidate]:
    if isinstance(node, ast.If):
        return _if_clause_candidates(node, lines, parents, headers, inline_headers)
    ####
    if isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
        return _loop_clause_candidates(node, lines, parents, headers, inline_headers)
    ####
    if isinstance(node, TRY_STATEMENTS):
        return _try_clause_candidates(node, lines, parents, headers, inline_headers)
    ####
    return []
####


def _is_discoverable_file(
        path: Path,
        root: Path,
        include_patterns: tuple[str, ...],
        exclude_patterns: tuple[str, ...],
        include_stubs: bool,
        include_markdown: bool,
) -> bool:
    """Return whether recursive discovery may process a supported regular file."""
    return _is_supported_source_file(
        path, root, include_patterns, include_stubs, include_markdown
    ) and not _is_excluded_path(path, root, exclude_patterns)
####


def _walk_python_files(
        root: Path,
        errors: MutableSequence[str],
        include_patterns: tuple[str, ...],
        exclude_patterns: tuple[str, ...],
        use_default_excludes: bool,
        include_stubs: bool,
        include_markdown: bool,
) -> set[Path]:
    files: set[Path] = set()

    def on_error(error: OSError) -> None:
        errors.append(f"{root}: {error}")
    ####


    for directory, names, filenames in os.walk(root, followlinks=False, onerror=on_error):
        current = Path(directory)
        kept_directories: list[str] = []
        for name in sorted(names):
            child = current / name
            if _should_prune_directory(
                    name, child, root, exclude_patterns, use_default_excludes
            ):
                continue
            ####
            kept_directories.append(name)
        ####
        names[:] = kept_directories
        for name in sorted(filenames):
            candidate = current / name
            if candidate.is_symlink() or not candidate.is_file():
                continue
            ####
            if _is_discoverable_file(
                    candidate,
                    root,
                    include_patterns,
                    exclude_patterns,
                    include_stubs,
                    include_markdown,
            ):
                files.add(candidate)
            ####
        ####
    ####
    return files
####


def _file_identity(path: Path) -> str:
    """Return a normalized identity for deduplicating equivalent path spellings."""
    try:
        return os.path.normcase(os.fspath(path.resolve(strict=False)))
    except OSError:
        return os.path.normcase(os.fspath(path.absolute()))
    ####
####


def _remember_file(files: dict[str, Path], path: Path) -> None:
    """Keep one deterministic, preferably relative display path per file."""
    identity = _file_identity(path)
    previous = files.get(identity)

    if previous is None:
        files[identity] = path
        return
    ####

    path_is_absolute = path.is_absolute()
    previous_is_absolute = previous.is_absolute()

    is_preferred = (
                           previous_is_absolute
                           and not path_is_absolute
                   ) or (
                           path_is_absolute == previous_is_absolute
                           and os.fspath(path) < os.fspath(previous)
                   )

    if is_preferred:
        files[identity] = path
    ####
####


def discover_python_files(
        paths: Iterable[Path],
        *,
        include_patterns: Iterable[str] = (),
        exclude_patterns: Iterable[str] = (),
        use_default_excludes: bool = True,
        include_stubs: bool = False,
        include_markdown: bool = False,
) -> tuple[list[Path], list[str]]:
    """Resolve source files, optionally including stubs and Markdown documents."""
    files: dict[str, Path] = {}
    errors: list[str] = []
    includes = tuple(include_patterns)
    patterns = tuple(exclude_patterns)
    for path in paths:
        try:
            if path.is_file():
                if not _is_supported_source_file(
                        path,
                        path.parent,
                        includes,
                        include_stubs,
                        include_markdown,
                ):
                    errors.append(f"{path}: expected a supported source file or directory")
                else:
                    _remember_file(files, path)
                ####
                continue
            ####
            if path.is_symlink() and path.is_dir():
                continue
            ####
            if path.is_dir():
                resolved_path = path.resolve()
                if _is_generated_root(path, use_default_excludes) or _matches_pattern(
                        resolved_path, resolved_path, patterns
                ):
                    continue
                ####
                for discovered in _walk_python_files(
                        path,
                        errors,
                        includes,
                        patterns,
                        use_default_excludes,
                        include_stubs,
                        include_markdown,
                ):
                    _remember_file(files, discovered)
                ####
                continue
            ####
            errors.append(f"{path}: path does not exist")
        except OSError as error:
            errors.append(f"{path}: {error}")
        ####
    ####
    return sorted(files.values()), errors
####


def python_files(
        paths: Iterable[Path],
        *,
        include_patterns: Iterable[str] = (),
        exclude_patterns: Iterable[str] = (),
        use_default_excludes: bool = True,
        include_stubs: bool = False,
        include_markdown: bool = False,
) -> list[Path]:
    """Discover source files without returning traversal diagnostics."""
    files, _ = discover_python_files(
        paths,
        include_patterns=include_patterns,
        exclude_patterns=exclude_patterns,
        use_default_excludes=use_default_excludes,
        include_stubs=include_stubs,
        include_markdown=include_markdown,
    )
    return files
####


def inspect_file(
        path: Path,
        *,
        mark_stubs: bool = False,
        indent_width: int | None = None,
        policy: MarkerPolicy | None = None,
) -> FileInspection:
    """Read and canonicalize one Python file without modifying it."""
    source, encoding = _read_source(path)
    formatted = format_source(
        source,
        filename=str(path),
        mark_stubs=mark_stubs,
        indent_width=indent_width,
        policy=policy,
    )
    return FileInspection(path=path, source=source, formatted=formatted, encoding=encoding)
####


def explain_file(
        path: Path,
        *,
        mark_stubs: bool = False,
        indent_width: int | None = None,
        policy: MarkerPolicy | None = None,
) -> tuple[BoundaryExplanation, ...]:
    """Read one Python file and explain every marker-boundary decision."""
    source, _ = _read_source(path)
    return explain_source(
        source,
        filename=str(path),
        mark_stubs=mark_stubs,
        indent_width=indent_width,
        policy=policy,
    )
####


def inspect_stripped_file(path: Path) -> FileInspection:
    """Read one file and prepare an inspection that removes scope markers."""
    source, encoding = _read_source(path)
    return FileInspection(
        path=path,
        source=source,
        formatted=strip_markers(source),
        encoding=encoding,
    )
####


def _write_atomic(path: Path, data: bytes) -> None:
    """Replace a file atomically while preserving its executable permission bits."""
    target = path.resolve(strict=True) if path.is_symlink() else path
    mode = stat.S_IMODE(target.stat().st_mode)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".scope-markers.tmp",
        dir=target.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        ####
        os.chmod(temporary, mode)
        os.replace(temporary, target)
    finally:
        with suppress(OSError):
            temporary.unlink(missing_ok=True)
        ####
    ####
####


def _error_message(path: Path, error: BaseException) -> str:
    if isinstance(error, SyntaxError):
        return f"{path}:{error.lineno or 0}:{error.offset or 0}: {error.msg}"
    ####
    if isinstance(error, tokenize.TokenError) and len(error.args) >= 2:
        message = error.args[0]
        location = error.args[1]
        if isinstance(message, str) and isinstance(location, tuple):
            location_values = cast(tuple[object, ...], location)
            if len(location_values) == 2:
                line, column = location_values
                if isinstance(line, int) and isinstance(column, int):
                    return f"{path}:{line}:{column}: {message}"
                ####
            ####
        ####
    ####
    return f"{path}: {error}"
####


def process_file(
        path: Path,
        *,
        fix: bool,
        mark_stubs: bool = False,
        indent_width: int | None = None,
        policy: MarkerPolicy | None = None,
) -> tuple[bool, str | None]:
    """Check or fix one file and return ``(changed, error)``."""
    try:
        inspection = inspect_file(
            path,
            mark_stubs=mark_stubs,
            indent_width=indent_width,
            policy=policy,
        )
        if inspection.changed and fix:
            _write_atomic(path, inspection.formatted.encode(inspection.encoding))
        ####
    except FILE_PROCESSING_ERRORS as error:
        return False, _error_message(path, error)
    ####
    return inspection.changed, None
####


def strip_file(path: Path, *, fix: bool) -> tuple[bool, str | None]:
    """Check or strip standalone scope markers from one file."""
    try:
        inspection = inspect_stripped_file(path)
        if inspection.changed and fix:
            _write_atomic(path, inspection.formatted.encode(inspection.encoding))
        ####
    except FILE_PROCESSING_ERRORS as error:
        return False, _error_message(path, error)
    ####
    return inspection.changed, None
####


def format_error(path: Path, error: BaseException) -> str:
    """Format a user-facing file-processing error for the CLI."""
    return _error_message(path, error)
####


def physical_lines(source: str) -> list[str]:
    """Expose physical line splitting to the CLI diff renderer."""
    return _physical_lines(source)
####


def write_atomic(path: Path, data: bytes) -> None:
    """Write encoded data atomically for the CLI."""
    _write_atomic(path, data)
####

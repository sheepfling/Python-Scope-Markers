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
from dataclasses import dataclass
from fnmatch import fnmatch
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from io import StringIO
from pathlib import Path
from typing import Final, cast

try:
    __version__ = package_version("scope-markers")
except PackageNotFoundError:
    __version__ = "0+unknown"
####


class ScopeMarkersError(ValueError):
    """Raised when source cannot be formatted under scope-marker rules."""
####


# ``####`` is the documented default; existing standalone markers can select
# ``##`` or ``####`` for compatibility with an already-formatted source tree.
MARKER: Final = "####"
MARKER_STYLES: Final = ("##", "####")
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
COMPOUND_STATEMENTS: Final = (
    *FUNCTION_STATEMENTS,
    ast.ClassDef,
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.With,
    ast.AsyncWith,
    ast.Try,
    getattr(ast, "TryStar", ast.Try),
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


def _standalone_marker_lines(source: str, marker: str) -> set[int]:
    lines = _physical_lines(source)
    marker_lines: set[int] = set()
    for token in _token_stream(source):
        if token.type != tokenize.COMMENT or token.string.rstrip(" \t\f") != marker:
            continue
        ####
        row, column = token.start
        if not 1 <= row <= len(lines):
            continue
        ####
        line = _line_body(lines[row - 1])
        before = line[:column]
        after = line[token.end[1]:]
        if not before.strip(" \t\f") and not after.strip(" \t\f"):
            marker_lines.add(row - 1)
        ####
    ####
    return marker_lines
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


def _compound_nodes(
        tree: ast.AST, lines: Sequence[str], *, mark_stubs: bool
) -> list[ast.stmt]:
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
        if not mark_stubs and _is_stub_function(node):
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


def _match_case_boundaries(tree: ast.AST, lines: Sequence[str]) -> list[ScopeBoundary]:
    case_header_lines = _match_case_header_lines(lines)
    boundaries: list[ScopeBoundary] = []
    for candidate in ast.walk(tree):
        if not isinstance(candidate, ast.Match):
            continue
        ####
        for case in candidate.cases:
            boundary = _match_case_boundary(case, lines, case_header_lines)
            if boundary is not None:
                boundaries.append(boundary)
            ####
        ####
    ####
    return boundaries
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
        mark_stubs: bool,
) -> list[ScopeBoundary]:
    boundaries = [
        _compound_boundary(node, lines)
        for node in _compound_nodes(tree, lines, mark_stubs=mark_stubs)
    ]
    boundaries.extend(_match_case_boundaries(tree, lines))
    return boundaries
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
    tokens_by_line: dict[int, list[tokenize.TokenInfo]] = {}
    for token in _token_stream(source):
        if token.start[0] in header_lines:
            tokens_by_line.setdefault(token.start[0], []).append(token)
        ####
    ####
    inline_headers: set[int] = set()
    ignored = {tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.ENDMARKER}
    for row, tokens in tokens_by_line.items():
        last_colon = max(
            (
                index
                for index, token in enumerate(tokens)
                if token.type == tokenize.OP and token.string == ":"
            ),
            default=-1,
        )
        if last_colon >= 0 and any(token.type not in ignored for token in tokens[last_colon + 1:]):
            inline_headers.add(row)
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
) -> str:
    """Return source with canonical markers after supported compound statements."""
    if indent_width is not None:
        source = _reindent_source(source, indent_width)
    ####
    marker = _detect_marker_style(source)
    clean_source = _without_markers(source, marker)
    tree = ast.parse(clean_source, filename=filename)
    lines = _physical_lines(clean_source)
    default_newline = _preferred_newline(clean_source or source)
    insertions: dict[int, list[ScopeBoundary]] = {}
    for boundary in _scope_boundaries(tree, lines, mark_stubs=mark_stubs):
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
) -> bool:
    return (
            path.suffix.casefold() == ".py"
            or (include_stubs and path.suffix.casefold() == ".pyi")
            or _matches_pattern(path, root, include_patterns)
    )
####


def _is_discoverable_file(
        path: Path,
        root: Path,
        include_patterns: tuple[str, ...],
        exclude_patterns: tuple[str, ...],
        include_stubs: bool,
) -> bool:
    """Return whether recursive discovery may process a supported regular file."""
    return _is_supported_source_file(
        path, root, include_patterns, include_stubs
    ) and not _is_excluded_path(path, root, exclude_patterns)
####


def _walk_python_files(
        root: Path,
        errors: MutableSequence[str],
        include_patterns: tuple[str, ...],
        exclude_patterns: tuple[str, ...],
        use_default_excludes: bool,
        include_stubs: bool,
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
            if candidate.is_symlink():
                continue
            ####
            if _is_discoverable_file(
                    candidate,
                    root,
                    include_patterns,
                    exclude_patterns,
                    include_stubs,
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
) -> tuple[list[Path], list[str]]:
    """Resolve inputs into Python files, optionally including ``.pyi`` stubs."""
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
) -> list[Path]:
    """Backward-compatible file discovery without returning diagnostics."""
    files, _ = discover_python_files(
        paths,
        include_patterns=include_patterns,
        exclude_patterns=exclude_patterns,
        use_default_excludes=use_default_excludes,
        include_stubs=include_stubs,
    )
    return files
####


def inspect_file(
        path: Path, *, mark_stubs: bool = False, indent_width: int | None = None
) -> FileInspection:
    """Read and canonicalize one Python file without modifying it."""
    source, encoding = _read_source(path)
    formatted = format_source(
        source,
        filename=str(path),
        mark_stubs=mark_stubs,
        indent_width=indent_width,
    )
    return FileInspection(path=path, source=source, formatted=formatted, encoding=encoding)
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
) -> tuple[bool, str | None]:
    """Check or fix one file and return ``(changed, error)``."""
    try:
        inspection = inspect_file(
            path, mark_stubs=mark_stubs, indent_width=indent_width
        )
        if inspection.changed and fix:
            _write_atomic(path, inspection.formatted.encode(inspection.encoding))
        ####
    except (
            OSError,
            SyntaxError,
            UnicodeError,
            tokenize.TokenError,
            ScopeMarkersError,
    ) as error:
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
    except (OSError, UnicodeError, tokenize.TokenError, ScopeMarkersError) as error:
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

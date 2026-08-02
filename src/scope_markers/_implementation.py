#!/usr/bin/env python3
"""Check or insert standalone ``####`` comments at Python scope boundaries."""

from __future__ import annotations

import ast
import os
import stat
import sys
import tempfile
import tokenize
from collections.abc import Iterable, Mapping, MutableSequence, Sequence
from dataclasses import dataclass
from fnmatch import fnmatch
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from io import BytesIO, StringIO
from pathlib import Path
from typing import Final, cast

try:
    __version__ = package_version("scope-markers")
except PackageNotFoundError:
    __version__ = "0+unknown"
####

MARKER: Final = "####"
MARKER_STYLES: Final = ("##", "####")
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
    encoding, _ = tokenize.detect_encoding(BytesIO(data).readline)
    return data.decode(encoding), encoding
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
    if index > 0:
        ending = _line_ending(lines[index - 1])
        if ending is not None:
            return ending
        ####
    ####
    if index < len(lines):
        ending = _line_ending(lines[index])
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


def _standalone_marker_lines(source: str, marker: str) -> set[int]:
    lines = _physical_lines(source)
    marker_lines: set[int] = set()
    stream = StringIO(source, newline="")
    for token in tokenize.generate_tokens(stream.readline):
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
        raise ValueError(f"conflicting standalone marker styles: {found}")
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


def _parents(tree: ast.AST) -> dict[int, ast.AST]:
    parents: dict[int, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[id(child)] = parent
        ####
    ####
    return parents
####


def _is_elif(node: ast.If, parents: Mapping[int, ast.AST]) -> bool:
    parent = parents.get(id(node))
    return (
            isinstance(parent, ast.If)
            and bool(parent.orelse)
            and parent.orelse[0] is node
            and parent.col_offset == node.col_offset
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


def _compound_nodes(tree: ast.AST, *, mark_stubs: bool) -> list[ast.stmt]:
    parents = _parents(tree)
    nodes: list[ast.stmt] = []
    for candidate in ast.walk(tree):
        if not isinstance(candidate, ast.stmt) or not isinstance(candidate, COMPOUND_STATEMENTS):
            continue
        ####
        node = candidate
        if isinstance(node, ast.If) and _is_elif(node, parents):
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
        raise ValueError(
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


def _match_case_boundaries(tree: ast.AST, lines: Sequence[str]) -> list[ScopeBoundary]:
    boundaries: list[ScopeBoundary] = []
    for candidate in ast.walk(tree):
        if not isinstance(candidate, ast.Match):
            continue
        ####
        for case in candidate.cases:
            if not case.body:
                continue
            ####
            line_number = getattr(case.pattern, "lineno", None)
            if not isinstance(line_number, int) or not 1 <= line_number <= len(lines):
                raise ValueError("match case has an invalid source location")
            ####
            indentation = _indentation_prefix(lines[line_number - 1])
            width = _indentation_width(indentation)
            boundaries.append(
                ScopeBoundary(
                    index=_insertion_index(lines, case.body[-1], width),
                    indentation=indentation,
                    indentation_width=width,
                    line_number=line_number,
                )
            )
        ####
    ####
    return boundaries
####


def _scope_boundaries(
        tree: ast.AST,
        lines: Sequence[str],
        *,
        mark_stubs: bool,
) -> list[ScopeBoundary]:
    boundaries: list[ScopeBoundary] = []
    for node in _compound_nodes(tree, mark_stubs=mark_stubs):
        if not 1 <= node.lineno <= len(lines):
            raise ValueError("compound statement has an invalid source location")
        ####
        indentation = _indentation_prefix(lines[node.lineno - 1])
        width = _indentation_width(indentation)
        boundaries.append(
            ScopeBoundary(
                index=_insertion_index(lines, node, width),
                indentation=indentation,
                indentation_width=width,
                line_number=node.lineno,
            )
        )
    ####
    boundaries.extend(_match_case_boundaries(tree, lines))
    return boundaries
####


def _ast_shape(tree: ast.AST) -> str:
    return ast.dump(tree, annotate_fields=True, include_attributes=False)
####


def format_source(
        source: str,
        *,
        filename: str = "<unknown>",
        mark_stubs: bool = False,
) -> str:
    """Return source with canonical markers after supported compound statements."""
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
    if _ast_shape(formatted_tree) != _ast_shape(tree):
        raise ValueError("scope-marker formatting changed the Python AST")
    ####
    return formatted
####


def _matches_pattern(path: Path, root: Path, patterns: tuple[str, ...]) -> bool:
    relative = path.relative_to(root).as_posix()
    return any(
        fnmatch(path.name, pattern)
        or fnmatch(relative, pattern)
        or fnmatch(path.as_posix(), pattern)
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
    return path.is_symlink() or _matches_pattern(path, root, patterns)
####


def _should_prune_directory(
        name: str,
        path: Path,
        root: Path,
        patterns: tuple[str, ...],
        use_default_excludes: bool,
) -> bool:
    return (
        (use_default_excludes and _is_skipped_directory(name))
        or _is_excluded_path(path, root, patterns)
    )
####


def _is_discoverable_file(
        path: Path,
        root: Path,
        include_patterns: tuple[str, ...],
        exclude_patterns: tuple[str, ...],
) -> bool:
    supported = (
            path.suffix.casefold() == ".py"
            or _matches_pattern(path, root, include_patterns)
    )
    return supported and not _is_excluded_path(path, root, exclude_patterns)
####


def _walk_python_files(
        root: Path,
        errors: MutableSequence[str],
        include_patterns: tuple[str, ...],
        exclude_patterns: tuple[str, ...],
        use_default_excludes: bool,
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
            if _is_discoverable_file(candidate, root, include_patterns, exclude_patterns):
                files.add(candidate)
            ####
        ####
    ####
    return files
####


def discover_python_files(
        paths: Iterable[Path],
        *,
        include_patterns: Iterable[str] = (),
        exclude_patterns: Iterable[str] = (),
        use_default_excludes: bool = True,
) -> tuple[list[Path], list[str]]:
    """Resolve explicit inputs into deterministic Python files and diagnostics."""
    files: set[Path] = set()
    errors: list[str] = []
    includes = tuple(include_patterns)
    patterns = tuple(exclude_patterns)
    for path in paths:
        try:
            if path.is_file():
                if (
                        path.suffix.casefold() != ".py"
                        and not _matches_pattern(path, path.parent, includes)
                ):
                    errors.append(f"{path}: expected a .py file or directory")
                else:
                    files.add(path)
                ####
                continue
            ####
            if path.is_dir():
                resolved_path = path.resolve()
                if _is_generated_root(path, use_default_excludes) or _matches_pattern(
                        resolved_path, resolved_path, patterns
                ):
                    continue
                ####
                files.update(
                    _walk_python_files(
                        path, errors, includes, patterns, use_default_excludes
                    )
                )
                continue
            ####
            errors.append(f"{path}: path does not exist")
        except OSError as error:
            errors.append(f"{path}: {error}")
        ####
    ####
    return sorted(files), errors
####


def python_files(
        paths: Iterable[Path],
        *,
        include_patterns: Iterable[str] = (),
        exclude_patterns: Iterable[str] = (),
        use_default_excludes: bool = True,
) -> list[Path]:
    """Backward-compatible file discovery without returning diagnostics."""
    files, _ = discover_python_files(
        paths,
        include_patterns=include_patterns,
        exclude_patterns=exclude_patterns,
        use_default_excludes=use_default_excludes,
    )
    return files
####


def inspect_file(path: Path, *, mark_stubs: bool = False) -> FileInspection:
    """Read and canonicalize one Python file without modifying it."""
    source, encoding = _read_source(path)
    formatted = format_source(source, filename=str(path), mark_stubs=mark_stubs)
    return FileInspection(path=path, source=source, formatted=formatted, encoding=encoding)
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
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
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
) -> tuple[bool, str | None]:
    """Check or fix one file and return ``(changed, error)``."""
    try:
        inspection = inspect_file(path, mark_stubs=mark_stubs)
        if inspection.changed and fix:
            _write_atomic(path, inspection.formatted.encode(inspection.encoding))
        ####
    except (OSError, SyntaxError, UnicodeError, tokenize.TokenError, ValueError) as error:
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

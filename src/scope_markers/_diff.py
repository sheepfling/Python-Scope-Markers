"""Render unified diffs for the command-line interface."""

from __future__ import annotations

import difflib
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from ._implementation import ScopeMarkersError, physical_lines
from .api import FileInspection


def _repository_root(start: Path) -> Path | None:
    """Return the enclosing repository root when one is visible."""
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
        ####
    ####
    return None
####


def _diff_path(path: Path) -> str:
    """Return a normalized, patch-safe path label."""
    absolute = path.resolve(strict=False)
    working_directory = Path.cwd().resolve()
    root = _repository_root(working_directory)
    if root is not None:
        try:
            absolute.relative_to(root)
        except ValueError:
            root = None
        ####
    ####
    if root is None:
        try:
            root = Path(os.path.commonpath((working_directory, absolute)))
        except ValueError:
            root = Path(absolute.anchor)
        ####
    ####
    try:
        return absolute.relative_to(root).as_posix()
    except ValueError:
        return absolute.name
    ####
####


def _quote_diff_path(path: str) -> str:
    """Quote non-ASCII path metadata using Git's C-style octal escapes."""
    if any(0xD800 <= ord(character) <= 0xDFFF for character in path):
        raw = os.fsencode(path)
    else:
        raw = path.encode("utf-8")
    ####
    if all(0x20 <= byte < 0x7F and byte not in b'"\\' for byte in raw):
        return path
    ####
    escaped: list[str] = ['"']
    for byte in raw:
        if byte == ord('"'):
            escaped.append('\\"')
        elif byte == ord("\\"):
            escaped.append("\\\\")
        elif byte == 9:
            escaped.append("\\t")
        elif byte == 10:
            escaped.append("\\n")
        elif byte == 13:
            escaped.append("\\r")
        elif 0x20 <= byte < 0x7F:
            escaped.append(chr(byte))
        else:
            escaped.append(f"\\{byte:03o}")
        ####
    ####
    escaped.append('"')
    return "".join(escaped)
####


def _diff_encoding(encoding: str) -> str:
    return "utf-8" if encoding.casefold() == "utf-8-sig" else encoding
####


BOM = "\N{ZERO WIDTH NO-BREAK SPACE}"


def _contains_bare_cr(source: str) -> bool:
    return any(line.endswith("\r") for line in physical_lines(source))
####


def render_diff(inspection: FileInspection) -> tuple[bytes, ...]:
    """Render a patch with normalized records and explicit EOF markers."""
    source = inspection.source
    formatted = inspection.formatted
    if _contains_bare_cr(source):
        raise ScopeMarkersError(
            "cannot render a patch for bare-CR line endings; "
            "use --fix or convert the file to LF or CRLF first"
        )
    ####
    if inspection.encoding.casefold() == "utf-8-sig":
        source = f"{BOM}{source}"
        formatted = f"{BOM}{formatted}"
    ####
    path = _diff_path(inspection.path)
    source_lines = _diff_lines(source)
    formatted_lines = _diff_lines(formatted)
    source_final_line = _final_diff_line(source)
    formatted_final_line = _final_diff_line(formatted)
    diff = difflib.unified_diff(
        source_lines,
        formatted_lines,
        fromfile=_quote_diff_path(f"a/{path}"),
        tofile=_quote_diff_path(f"b/{path}"),
    )
    output: list[str] = []
    for index, line in enumerate(diff):
        output.append(line.replace("\x00", ""))
        if index < 2:
            continue
        ####
        if _is_missing_final_newline(line, source_final_line, formatted_final_line):
            output.append("\\ No newline at end of file\n")
        ####
    ####
    encoding = _diff_encoding(inspection.encoding)
    return tuple(
        line.encode("utf-8" if index < 2 else encoding)
        for index, line in enumerate(output)
    )
####


def write_diff(diff: Sequence[bytes], encoding: str) -> None:
    """Write diff bytes without platform newline translation."""
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is None:
        output_encoding = _diff_encoding(encoding)
        errors = sys.stdout.errors or "strict"
        for index, line in enumerate(diff):
            line_encoding = "utf-8" if index < 2 else output_encoding
            sys.stdout.write(line.decode(line_encoding, errors))
        ####
        return
    ####
    for line in diff:
        buffer.write(line)
    ####
####


def _is_missing_final_newline(
        line: str,
        source_final_line: str | None,
        formatted_final_line: str | None,
) -> bool:
    if not line or line[0] not in "-+":
        if line and line[0] == " ":
            return (
                    source_final_line is not None
                    and formatted_final_line is not None
                    and line[1:] == source_final_line == formatted_final_line
            )
        ####
        return False
    ####
    expected = source_final_line if line[0] == "-" else formatted_final_line
    return expected is not None and line[1:] == expected
####


def _diff_lines(source: str) -> list[str]:
    """Return diff records while preserving CRLF content endings."""
    lines: list[str] = []
    for line in physical_lines(source):
        if line.endswith("\r\n"):
            # Keep CRLF in the record so patches apply to CRLF files. The
            # The embedded CRLF supplies the record ending required by difflib.
            lines.append(line)
        elif line.endswith(("\r", "\n")):
            # Bare CR is unreachable from the CLI, which rejects it before
            # rendering; keep the fallback for direct internal callers.
            lines.append(f"{line[:-1]}\n")
        else:
            lines.append(f"{line}\x00\n")
        ####
    ####
    return lines
####


def _final_diff_line(source: str) -> str | None:
    """Return the normalized final record when the source lacks a newline."""
    if not source or source.endswith(("\r", "\n")):
        return None
    ####
    return _diff_lines(source)[-1]
####

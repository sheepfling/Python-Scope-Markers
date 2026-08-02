"""Command-line interface for scope markers."""

from __future__ import annotations

import argparse
import difflib
import sys
import tokenize
from collections.abc import Sequence
from pathlib import Path

from ._implementation import (
    format_error,
    physical_lines,
    write_atomic,
)
from .api import (
    FileInspection,
    __version__,
    discover_python_files,
    inspect_file,
)


def _unified_diff(inspection: FileInspection) -> str:
    """Render a patch with normalized records and explicit EOF markers."""
    source = inspection.source
    formatted = inspection.formatted
    path = inspection.path
    source_lines = _diff_lines(source)
    formatted_lines = _diff_lines(formatted)
    source_final_line = _final_diff_line(source)
    formatted_final_line = _final_diff_line(formatted)
    diff = difflib.unified_diff(
        source_lines,
        formatted_lines,
        fromfile=str(path),
        tofile=str(path),
    )
    output: list[str] = []
    for line in diff:
        output.append(line.replace("\x00", ""))
        if line.startswith(("---", "+++")):
            continue
        ####
        if _is_missing_final_newline(line, source_final_line, formatted_final_line):
            output.append("\\ No newline at end of file\n")
        ####
    ####
    return "".join(output)
####


def _is_missing_final_newline(
        line: str,
        source_final_line: str | None,
        formatted_final_line: str | None,
) -> bool:
    if not line or line[0] not in "-+":
        return False
    ####
    expected = source_final_line if line[0] == "-" else formatted_final_line
    return expected is not None and line[1:] == expected
####


def _diff_lines(source: str) -> list[str]:
    """Return LF-delimited records suitable for unified diff output."""
    lines: list[str] = []
    for line in physical_lines(source):
        if line.endswith("\r\n"):
            line = line[:-2]
        elif line.endswith(("\r", "\n")):
            line = line[:-1]
        ####
        lines.append(f"{line}\n")
    ####
    if lines and source and not source.endswith(("\r", "\n")):
        lines[-1] = f"{lines[-1][:-1]}\x00\n"
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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--fix", action="store_true", help="rewrite files in place")
    mode.add_argument("--diff", action="store_true", help="print a unified diff without rewriting")
    parser.add_argument(
        "--mark-stubs",
        action="store_true",
        help="also mark documentation-only and ellipsis-only function stubs",
    )
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--quiet", action="store_true", help="suppress status output")
    output.add_argument("--verbose", action="store_true", help="report each processed file")
    parser.add_argument(
        "--no-default-excludes",
        action="store_true",
        help="also scan normally skipped directories such as .git and .venv",
    )
    parser.add_argument(
        "--include",
        action="append",
        default=[],
        metavar="PATTERN",
        help="include additional recursively discovered paths matching this glob (repeatable)",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="PATTERN",
        help="skip recursively discovered paths matching this glob (repeatable)",
    )
    parser.add_argument("--version", action="version", version=f"scope-markers {__version__}")
    parser.add_argument("paths", nargs="*", type=Path, default=[Path(".")])
    return parser
####


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    paths = [Path(path) for path in args.paths]
    fix = bool(args.fix)
    show_diff = bool(args.diff)
    mark_stubs = bool(args.mark_stubs)
    quiet = bool(args.quiet)
    verbose = bool(args.verbose)
    include_patterns = tuple(args.include)
    exclude_patterns = tuple(args.exclude)
    use_default_excludes = not bool(args.no_default_excludes)

    files, errors = discover_python_files(
        paths,
        include_patterns=include_patterns,
        exclude_patterns=exclude_patterns,
        use_default_excludes=use_default_excludes,
    )
    changed: list[Path] = []
    for path in files:
        try:
            inspection = inspect_file(path, mark_stubs=mark_stubs)
            if not inspection.changed:
                if verbose:
                    print(f"clean: {path}", file=sys.stderr if show_diff else sys.stdout)
                ####
                continue
            ####
            changed.append(path)
            if show_diff:
                sys.stdout.write(_unified_diff(inspection))
                if verbose:
                    print(f"needs markers: {path}", file=sys.stderr)
                ####
            elif fix:
                write_atomic(path, inspection.formatted.encode(inspection.encoding))
                if not quiet:
                    print(f"fixed: {path}")
                ####
            elif verbose or not quiet:
                print(f"needs markers: {path}")
            ####
        except (OSError, SyntaxError, UnicodeError, tokenize.TokenError, ValueError) as error:
            errors.append(format_error(path, error))
        ####
    ####

    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 2
    ####
    if changed and not fix:
        return 1
    ####
    if not quiet:
        action = "fixed" if fix else "clean"
        print(f"scope markers {action} ({len(files)} files)")
    ####
    return 0
####

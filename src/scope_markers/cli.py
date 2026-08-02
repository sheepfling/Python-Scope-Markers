"""Command-line interface for scope markers."""

from __future__ import annotations

import argparse
import difflib
import sys
import tokenize
from collections.abc import Sequence
from pathlib import Path

from ._implementation import (
    FileInspection,
    __version__,
    discover_python_files,
    format_error,
    inspect_file,
    physical_lines,
    write_atomic,
)

def _unified_diff(inspection: FileInspection) -> str:
    source = inspection.source
    formatted = inspection.formatted
    path = inspection.path
    return "".join(
        difflib.unified_diff(
            physical_lines(source),
            physical_lines(formatted),
            fromfile=str(path),
            tofile=str(path),
        )
    )
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
    parser.add_argument("--quiet", action="store_true", help="suppress clean and fixed-file output")
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
    exclude_patterns = tuple(args.exclude)

    files, errors = discover_python_files(paths, exclude_patterns=exclude_patterns)
    changed: list[Path] = []
    for path in files:
        try:
            inspection = inspect_file(path, mark_stubs=mark_stubs)
            if not inspection.changed:
                continue
            ####
            changed.append(path)
            if show_diff:
                sys.stdout.write(_unified_diff(inspection))
            elif fix:
                write_atomic(path, inspection.formatted.encode(inspection.encoding))
                if not quiet:
                    print(f"fixed: {path}")
                ####
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
        if not show_diff and not quiet:
            for path in changed:
                print(f"needs markers: {path}")
            ####
        ####
        return 1
    ####
    if not quiet:
        action = "fixed" if fix else "clean"
        print(f"scope markers {action} ({len(files)} files)")
    ####
    return 0
####

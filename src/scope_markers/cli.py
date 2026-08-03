"""Command-line interface for scope markers."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from ._diff import render_diff, write_diff
from ._implementation import (
    FILE_PROCESSING_ERRORS,
    MARKDOWN_SUFFIXES,
    format_error,
    write_atomic,
)
from ._markdown import inspect_markdown_file
from .api import (
    __version__,
    discover_python_files,
    inspect_file,
    inspect_stripped_file,
)

_DESCRIPTION = """Inspect Python source or Python Markdown fences and add or remove
standalone scope-marker comments.

The default mode checks files without changing them and exits with status 1 when
markers would be added or regenerated. Use --fix to rewrite files, or --diff to
print the proposed changes as a unified diff. With no PATH arguments, the
current directory is discovered recursively.
"""

_EPILOG = """examples:
  scope-markers src tests
  scope-markers --diff src tests
  scope-markers --fix --indent-width 2 src
  scope-markers --strip --fix src tests
  scope-markers --markdown --fix README.md

Use --help with a command installed as either `scope-markers` or
`python -m scope_markers`."""


def _positive_indent_width(value: str) -> int:
    try:
        width = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a positive integer") from error
    ####
    if width < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    ####
    return width
####


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=_DESCRIPTION,
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--fix",
        action="store_true",
        help="apply the requested marker operation and indentation changes in place",
    )
    mode.add_argument(
        "--diff",
        action="store_true",
        help="print a unified diff to standard output without rewriting files",
    )
    parser.add_argument(
        "--strip",
        action="store_true",
        help="remove standalone scope-marker comments instead of adding or regenerating them",
    )
    parser.add_argument(
        "--mark-stubs",
        action="store_true",
        help="include recursively discovered .pyi files; mark documentation-only "
        "and ellipsis-only definitions",
    )
    parser.add_argument(
        "--markdown",
        action="store_true",
        help="process Python code fences in recursively discovered .md and .markdown files",
    )
    parser.add_argument(
        "--indent-width",
        type=_positive_indent_width,
        metavar="WIDTH",
        help="normalize logical block indentation to WIDTH spaces before marking "
        "(cannot be combined with --strip)",
    )
    output = parser.add_mutually_exclusive_group()
    output.add_argument(
        "--quiet",
        action="store_true",
        help="suppress normal status and summary output; diagnostics remain visible",
    )
    output.add_argument(
        "--verbose",
        action="store_true",
        help="report the status of every processed file, including clean files",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="stop after the first changed file or processing/discovery error",
    )
    parser.add_argument(
        "--no-default-excludes",
        action="store_true",
        help="scan directories normally pruned, such as .git and .venv "
        "(explicit --exclude patterns still apply)",
    )
    parser.add_argument(
        "--include",
        action="append",
        default=[],
        metavar="PATTERN",
        help="include additional recursively discovered paths matching this glob; "
        "repeat for multiple patterns",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="PATTERN",
        help="skip recursively discovered paths matching this glob; repeat for "
        "multiple patterns (explicit files are still processed)",
    )
    parser.add_argument("--version", action="version", version=f"scope-markers {__version__}")
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        default=[Path(".")],
        metavar="PATH",
        help="file or directory to inspect; directories are recursive "
        "(default: current directory)",
    )
    return parser
####


def _report_errors(errors: Sequence[str]) -> None:
    """Write collected diagnostics to standard error."""
    print("\n".join(errors), file=sys.stderr)
####


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    paths = [Path(path) for path in args.paths]
    fix = bool(args.fix)
    show_diff = bool(args.diff)
    strip = bool(args.strip)
    mark_stubs = bool(args.mark_stubs)
    include_markdown = bool(args.markdown)
    indent_width = args.indent_width if isinstance(args.indent_width, int) else None
    quiet = bool(args.quiet)
    verbose = bool(args.verbose)
    fail_fast = bool(args.fail_fast)
    include_patterns = tuple(args.include)
    exclude_patterns = tuple(args.exclude)
    use_default_excludes = not bool(args.no_default_excludes)
    if strip and indent_width is not None:
        parser.error("--indent-width cannot be used with --strip")
    ####

    files, errors = discover_python_files(
        paths,
        include_patterns=include_patterns,
        exclude_patterns=exclude_patterns,
        use_default_excludes=use_default_excludes,
        include_stubs=mark_stubs,
        include_markdown=include_markdown,
    )
    if errors and fail_fast:
        _report_errors(errors)
        return 2
    ####
    changed: list[Path] = []
    processed_files = 0
    for path in files:
        processed_files += 1
        try:
            if include_markdown and path.suffix.casefold() in MARKDOWN_SUFFIXES:
                inspection = inspect_markdown_file(
                    path,
                    mark_stubs=mark_stubs,
                    indent_width=indent_width,
                    strip=strip,
                )
            elif strip:
                inspection = inspect_stripped_file(path)
            else:
                inspection = inspect_file(
                    path, mark_stubs=mark_stubs, indent_width=indent_width
                )
            ####
            if not inspection.changed:
                if verbose:
                    print(f"clean: {path}", file=sys.stderr if show_diff else sys.stdout)
                ####
                continue
            ####
            changed.append(path)
            if show_diff:
                write_diff(render_diff(inspection), inspection.encoding)
                if verbose:
                    message = "markers to strip" if strip else "needs markers"
                    print(f"{message}: {path}", file=sys.stderr)
                ####
            elif fix:
                write_atomic(path, inspection.formatted.encode(inspection.encoding))
                if not quiet:
                    action = "stripped" if strip else "fixed"
                    print(f"{action}: {path}")
                ####
            elif verbose or not quiet:
                message = "markers to strip" if strip else "needs markers"
                print(f"{message}: {path}")
            ####
            if fail_fast:
                break
            ####
        except FILE_PROCESSING_ERRORS as error:
            errors.append(format_error(path, error))
            if fail_fast:
                break
            ####
        ####
    ####

    if errors:
        _report_errors(errors)
        return 2
    ####
    if changed and not fix:
        return 1
    ####
    if not quiet:
        if fix:
            if strip:
                action = "stripped" if changed else "already stripped"
            else:
                action = "fixed" if changed else "already clean"
            ####
            count = len(changed) if changed else processed_files
        else:
            action = "clean"
            count = processed_files if fail_fast else len(files)
        ####
        print(
            f"scope markers {action} ({count} files)",
            file=sys.stderr if show_diff else sys.stdout,
        )
    ####
    return 0
####

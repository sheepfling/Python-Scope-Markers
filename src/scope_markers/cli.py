"""Command-line interface for scope markers."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from ._diff import render_diff, write_diff
from ._implementation import (
    FILE_PROCESSING_ERRORS,
    MARKDOWN_SUFFIXES,
    format_error,
    write_atomic,
)
from ._markdown import inspect_markdown_file
from ._paths import display_path
from ._policy import (
    MarkerPolicy,
    PolicyError,
    describe_policy,
    find_config,
    list_selectors,
    policy_with_cli_overrides,
    resolve_policy,
)
from .api import (
    __version__,
    discover_python_files,
    explain_file,
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


def _non_negative_integer(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a non-negative integer") from error
    ####
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be a non-negative integer")
    ####
    return parsed
####


def _non_empty_pattern(value: str) -> str:
    if not value:
        raise argparse.ArgumentTypeError("must not be empty")
    ####
    return value
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
    policy = parser.add_argument_group("marker policy")
    policy.add_argument("--preset", metavar="NAME", help="use a named marker-policy preset")
    policy.add_argument(
        "--select",
        action="append",
        default=[],
        metavar="SELECTOR",
        help="replace configured selectors; repeat or separate selectors with commas",
    )
    policy.add_argument(
        "--extend-select",
        action="append",
        default=[],
        metavar="SELECTOR",
        help="add selectors; repeat or separate selectors with commas",
    )
    policy.add_argument(
        "--ignore",
        action="append",
        default=[],
        metavar="SELECTOR",
        help="remove selectors; repeat or separate selectors with commas",
    )
    policy.add_argument(
        "--skip-inline-suites",
        action="store_true",
        default=None,
        help="do not mark suites whose body starts on the header line",
    )
    policy.add_argument(
        "--min-span-lines",
        type=_non_negative_integer,
        metavar="N",
        help="require candidates to span at least N physical lines",
    )
    policy.add_argument(
        "--min-body-lines",
        type=_non_negative_integer,
        metavar="N",
        help="require at least one owned suite to span N physical lines",
    )
    policy.add_argument(
        "--min-body-statements",
        type=_non_negative_integer,
        metavar="N",
        help="require at least one owned suite to contain N direct statements",
    )
    policy.add_argument(
        "--min-clauses",
        type=_non_negative_integer,
        metavar="N",
        help="require candidates to own at least N suites or branches",
    )
    policy.add_argument(
        "--min-depth",
        type=_non_negative_integer,
        metavar="N",
        help="only mark candidates nested at least N compound statements",
    )
    policy.add_argument(
        "--max-depth",
        type=_non_negative_integer,
        metavar="N",
        help="do not mark candidates nested deeper than N compound statements",
    )
    configuration = policy.add_mutually_exclusive_group()
    configuration.add_argument("--config", type=Path, metavar="PATH", help="use one TOML config")
    configuration.add_argument(
        "--isolated",
        action="store_true",
        help="ignore a configuration discovered from the current directory",
    )
    policy.add_argument(
        "--show-settings",
        type=Path,
        metavar="PATH",
        help="print the resolved policy for PATH and exit",
    )
    policy.add_argument(
        "--explain",
        type=Path,
        metavar="PATH",
        help="report why each candidate in one Python file will be marked or skipped",
    )
    policy.add_argument(
        "--list-selectors",
        action="store_true",
        help="print supported policy presets, groups, and selectors, then exit",
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
        type=_non_empty_pattern,
        metavar="PATTERN",
        help="include additional recursively discovered paths matching this glob; "
        "repeat for multiple patterns",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        type=_non_empty_pattern,
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


def _preflight_policies(
        paths: Sequence[Path], resolver: Callable[[Path], MarkerPolicy]
) -> tuple[dict[Path, MarkerPolicy], tuple[str, ...]]:
    """Resolve every policy before any file can be inspected or rewritten."""
    policies: dict[Path, MarkerPolicy] = {}
    errors: list[str] = []
    for path in paths:
        try:
            policies[path] = resolver(path)
        except PolicyError as error:
            errors.append(format_error(path, error))
        ####
    ####
    return policies, tuple(errors)
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
    policy_option_used = any(
        (
            args.preset is not None,
            bool(args.select),
            bool(args.extend_select),
            bool(args.ignore),
            args.skip_inline_suites is not None,
            args.min_span_lines is not None,
            args.min_body_lines is not None,
            args.min_body_statements is not None,
            args.min_clauses is not None,
            args.min_depth is not None,
            args.max_depth is not None,
        )
    )
    if strip and policy_option_used:
        parser.error("marker-policy options cannot be used with --strip")
    ####
    if bool(args.list_selectors):
        print(list_selectors())
        return 0
    ####
    if args.show_settings is not None and args.explain is not None:
        parser.error("--show-settings cannot be used with --explain")
    ####

    def resolved_policy(path: Path) -> MarkerPolicy:
        config = args.config
        if config is None and not bool(args.isolated):
            config = find_config(path)
        ####
        return policy_with_cli_overrides(
            resolve_policy(config, path),
            preset=args.preset,
            select=tuple(args.select),
            extend_select=tuple(args.extend_select),
            ignore=tuple(args.ignore),
            skip_inline_suites=args.skip_inline_suites,
            min_span_lines=args.min_span_lines,
            min_body_lines=args.min_body_lines,
            min_body_statements=args.min_body_statements,
            min_clauses=args.min_clauses,
            min_depth=args.min_depth,
            max_depth=args.max_depth,
            mark_stubs=mark_stubs,
        )
    ####
    if args.show_settings is not None:
        try:
            print(describe_policy(resolved_policy(args.show_settings)))
        except PolicyError as error:
            parser.error(str(error))
        ####
        return 0
    ####
    if args.explain is not None:
        if strip:
            parser.error("--explain cannot be used with --strip")
        ####
        if fix or show_diff:
            parser.error("--explain cannot be used with --fix or --diff")
        ####
        if include_markdown or args.explain.suffix.casefold() in MARKDOWN_SUFFIXES:
            parser.error("--explain currently supports Python source files, not Markdown")
        ####
        try:
            marker_policy = resolved_policy(args.explain)
            explanations = explain_file(
                    args.explain,
                    mark_stubs=mark_stubs,
                    indent_width=indent_width,
                    policy=marker_policy,
            )
            if not explanations:
                print(f"{display_path(args.explain)}: no boundary candidates")
            ####
            for explanation in explanations:
                action = "mark" if explanation.will_mark else "skip"
                print(
                    f"{display_path(args.explain)}:{explanation.line_number}: {action} "
                    f"{explanation.kind}: {explanation.reason}"
                )
            ####
        except FILE_PROCESSING_ERRORS as error:
            parser.error(format_error(args.explain, error))
        ####
        return 0
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
    resolved_policies: dict[Path, MarkerPolicy] = {}
    if not strip:
        policy_targets = files if files else paths
        resolved_policies, policy_errors = _preflight_policies(
            policy_targets, resolved_policy
        )
        if policy_errors:
            errors.extend(policy_errors)
            _report_errors(errors)
            return 2
        ####
    ####
    changed: list[Path] = []
    processed_files = 0
    for path in files:
        processed_files += 1
        try:
            if strip:
                if include_markdown and path.suffix.casefold() in MARKDOWN_SUFFIXES:
                    inspection = inspect_markdown_file(
                        path,
                        mark_stubs=mark_stubs,
                        indent_width=indent_width,
                        strip=True,
                    )
                else:
                    inspection = inspect_stripped_file(path)
                ####
            else:
                marker_policy = resolved_policies[path]
                if include_markdown and path.suffix.casefold() in MARKDOWN_SUFFIXES:
                    inspection = inspect_markdown_file(
                        path,
                        mark_stubs=mark_stubs,
                        indent_width=indent_width,
                        strip=strip,
                        policy=marker_policy,
                    )
                else:
                    inspection = inspect_file(
                        path,
                        mark_stubs=mark_stubs,
                        indent_width=indent_width,
                        policy=marker_policy,
                    )
                ####
            ####
            if not inspection.changed:
                if verbose:
                    print(
                        f"clean: {display_path(path)}",
                        file=sys.stderr if show_diff else sys.stdout,
                    )
                ####
                continue
            ####
            changed.append(path)
            if show_diff:
                write_diff(render_diff(inspection), inspection.encoding)
                if verbose:
                    message = "markers to strip" if strip else "needs markers"
                    print(f"{message}: {display_path(path)}", file=sys.stderr)
                ####
            elif fix:
                write_atomic(path, inspection.formatted.encode(inspection.encoding))
                if not quiet:
                    action = "stripped" if strip else "fixed"
                    print(f"{action}: {display_path(path)}")
                ####
            elif verbose or not quiet:
                message = "markers to strip" if strip else "needs markers"
                print(f"{message}: {display_path(path)}")
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

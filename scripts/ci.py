"""Run the repository's CI checks locally and in GitHub Actions."""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def ci_commands(
    python: str = sys.executable,
    *,
    fix: bool = False,
) -> tuple[tuple[str, ...], ...]:
    """Return the ordered, platform-independent commands used by CI."""
    ruff = (python, "-m", "ruff", "check")
    if fix:
        ruff += ("--fix",)
    ####
    ruff += ("src", "scripts", "tests")
    scope_markers = ("scope-markers",)
    if fix:
        scope_markers += ("--fix",)
    ####
    scope_markers += ("src", "scripts", "tests")
    return (
        (python, "-m", "pytest", "-q"),
        (python, "scripts/check_diff.py"),
        ruff,
        (python, "-m", "flake8", "src", "scripts", "tests"),
        (python, "scripts/check_black.py"),
        (python, "scripts/check_pyright.py"),
        (python, "scripts/check_build.py"),
        scope_markers,
    )
####


def run_command(command: Sequence[str]) -> int:
    """Run one CI command from the repository root and return its exit code."""
    try:
        completed = subprocess.run(command, cwd=ROOT, check=False)
    except OSError as error:
        print(f"CI command could not start: {' '.join(command)}: {error}", file=sys.stderr)
        return 1
    ####
    return completed.returncode
####


def main(argv: Sequence[str] = ()) -> int:
    """Run each CI command in order, stopping at the first failure."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fix",
        action="store_true",
        help="allow Ruff and scope-markers to rewrite files during validation",
    )
    args = parser.parse_args(argv)
    commands = ci_commands(fix=True) if args.fix else ci_commands()
    for command in commands:
        print(f"$ {' '.join(command)}")
        return_code = run_command(command)
        if return_code:
            return return_code
        ####
    ####
    return 0
####


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
####

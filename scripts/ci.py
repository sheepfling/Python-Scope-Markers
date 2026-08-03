"""Run the repository's CI checks locally and in GitHub Actions."""

from __future__ import annotations

import argparse
import os
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
    scope_markers = (python, "-m", "scope_markers")
    if fix:
        scope_markers += ("--fix",)
    ####
    scope_markers += ("src", "scripts", "tests")
    rumdl = (python, "scripts/check_rumdl.py")
    if fix:
        rumdl += ("--fix",)
    ####
    return (
        (python, "-m", "pytest", "-q"),
        (python, "scripts/check_diff.py"),
        ruff,
        (python, "-m", "flake8", "src", "scripts", "tests"),
        (python, "scripts/check_black.py"),
        (python, "scripts/check_pyright.py"),
        (python, "scripts/check_build.py"),
        scope_markers,
        rumdl,
    )
####


def run_command(command: Sequence[str]) -> int:
    """Run one CI command from the repository root and return its exit code."""
    environment = os.environ.copy()
    source_path = str(ROOT / "src")
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = os.pathsep.join(
        path for path in (source_path, existing_pythonpath) if path
    )
    try:
        completed = subprocess.run(command, cwd=ROOT, env=environment, check=False)
    except OSError as error:
        print(f"CI command could not start: {' '.join(command)}: {error}", file=sys.stderr)
        return 1
    ####
    return completed.returncode
####


def main(argv: Sequence[str] = ()) -> int:
    """Run each CI command in order, stopping at the first failure."""
    parser = argparse.ArgumentParser(
        description=(
            "Run the repository's checks in the same order as CI, stopping at "
            "the first failure."
        ),
        epilog=(
            "By default every check is read-only. With --fix, Ruff, scope-markers, "
            "and rumdl may update files as part of validation.\n\n"
            "examples:\n"
            "  python -m scripts.ci\n"
            "  python -m scripts.ci --fix"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="allow Ruff, scope-markers, and rumdl to rewrite files during validation",
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

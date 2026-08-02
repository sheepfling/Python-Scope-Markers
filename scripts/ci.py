"""Run the repository's CI checks locally and in GitHub Actions."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def ci_commands(python: str = sys.executable) -> tuple[tuple[str, ...], ...]:
    """Return the ordered, platform-independent commands used by CI."""
    return (
        (python, "-m", "pytest", "-q"),
        (python, "-m", "ruff", "check", "."),
        (python, "-m", "flake8", "src", "scripts", "tests"),
        (python, "scripts/check_black.py"),
        (python, "-m", "pyright"),
        (python, "-m", "build", "--wheel"),
        ("scope-markers", "."),
    )
####


def run_command(command: Sequence[str]) -> int:
    """Run one CI command from the repository root and return its exit code."""
    completed = subprocess.run(command, cwd=ROOT, check=False)
    return completed.returncode
####


def main() -> int:
    """Run each CI command in order, stopping at the first failure."""
    for command in ci_commands():
        print(f"$ {' '.join(command)}")
        return_code = run_command(command)
        if return_code:
            return return_code
        ####
    ####
    return 0
####


if __name__ == "__main__":
    raise SystemExit(main())
####

"""Validate CLI diff bytes with Git's patch consumer."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

DIFF_CASES: tuple[tuple[str, Path, bytes], ...] = (
    (
        "lf",
        Path("src/example.py"),
        b"def example():\n    value = 'hello'\n",
    ),
    (
        "crlf",
        Path("src/example.py"),
        b"def example():\r\n    value = 'hello'\r\n",
    ),
    (
        "utf8",
        Path("src/example.py"),
        b"# coding: utf-8\ndef example():\n    value = 'h\xc3\xa9llo'\n",
    ),
    (
        "cp1252-unicode-path",
        Path("emoji-\U0001f600/example.py"),
        b"# coding: cp1252\ndef example():\n    value = 'h\xe9llo'\n",
    ),
    (
        "utf8-bom",
        Path("src/example.py"),
        b"\xef\xbb\xbfdef example():\n    pass\n",
    ),
)


def _run_diff_case(git: str, name: str, relative: Path, source: bytes) -> str | None:
    with TemporaryDirectory(prefix=f"scope-markers-diff-{name}-") as raw:
        root = Path(raw)
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(source)
        initialized = subprocess.run(
            [git, "init", "--quiet"], cwd=root, check=False, capture_output=True
        )
        if initialized.returncode:
            return initialized.stderr.decode(errors="replace")
        ####
        completed = subprocess.run(
            [sys.executable, "-m", "scope_markers", "--diff", str(path)],
            cwd=root,
            check=False,
            capture_output=True,
        )
        if completed.returncode != 1:
            stderr = completed.stderr.decode(errors="replace")
            return f"CLI returned {completed.returncode}: {stderr}"
        ####
        patch = root / "change.patch"
        patch.write_bytes(completed.stdout)
        checked = subprocess.run(
            [git, "apply", "--check", str(patch)],
            cwd=root,
            check=False,
            capture_output=True,
        )
        if checked.returncode:
            return checked.stderr.decode(errors="replace")
        ####
    ####
    return None
####


def _check_bare_cr(git: str) -> str | None:
    with TemporaryDirectory(prefix="scope-markers-diff-bare-cr-") as raw:
        root = Path(raw)
        path = root / "example.py"
        path.write_bytes(b"def example():\r    pass\r")
        completed = subprocess.run(
            [sys.executable, "-m", "scope_markers", "--diff", str(path)],
            cwd=root,
            check=False,
            capture_output=True,
        )
        if completed.returncode != 2 or completed.stdout:
            return f"CLI returned {completed.returncode} with unexpected patch output"
        ####
        if b"bare-CR line endings" not in completed.stderr:
            return "CLI did not explain the bare-CR limitation"
        ####
    ####
    return None
####


def main() -> int:
    """Run diff contract checks against a real Git worktree."""
    git = shutil.which("git")
    if git is None:
        print("diff contract check requires git on PATH", file=sys.stderr)
        return 1
    ####
    for name, relative, source in DIFF_CASES:
        failure = _run_diff_case(git, name, relative, source)
        if failure is not None:
            print(f"diff contract failed for {name}: {failure}", file=sys.stderr)
            return 1
        ####
    ####
    failure = _check_bare_cr(git)
    if failure is not None:
        print(f"diff contract failed for bare-CR input: {failure}", file=sys.stderr)
        return 1
    ####
    print(f"diff contract passed ({len(DIFF_CASES)} applicable cases and bare-CR rejection)")
    return 0
####


if __name__ == "__main__":
    raise SystemExit(main())
####

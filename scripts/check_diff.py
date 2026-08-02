"""Validate CLI diff bytes with Git's patch consumer."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from scope_markers.api import inspect_file

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
        "mixed-newlines",
        Path("src/example.py"),
        b"def first():\r\n    pass\r\ndef second():\n    pass\n",
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
        "space-path",
        Path("space path/example.py"),
        b"def example():\n    value = 'hello'\n",
    ),
    (
        "utf8-bom",
        Path("src/example.py"),
        b"\xef\xbb\xbfdef example():\n    pass\n",
    ),
)
AUTOCRLF_MODES = ("false", "true", "input")

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
            [git, "-c", "core.autocrlf=false", "apply", "--check", str(patch)],
            cwd=root,
            check=False,
            capture_output=True,
        )
        if checked.returncode:
            return checked.stderr.decode(errors="replace")
        ####
        inspection = inspect_file(path)
        expected = inspection.formatted.encode(inspection.encoding)
        applied = subprocess.run(
            [git, "-c", "core.autocrlf=false", "apply", str(patch)],
            cwd=root,
            check=False,
            capture_output=True,
        )
        if applied.returncode:
            return applied.stderr.decode(errors="replace")
        ####
        if path.read_bytes() != expected:
            return "git apply did not produce the formatter's expected bytes"
        ####
    ####
    return None
####


def _check_bare_cr() -> str | None:
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


def _check_newline_filename(git: str) -> str | None:
    """Verify a real newline-bearing filename on filesystems that permit it."""
    if os.name == "nt":
        return None
    ####
    with TemporaryDirectory(prefix="scope-markers-diff-newline-name-") as raw:
        root = Path(raw)
        path = root / "line\nbreak.py"
        path.write_text("def example():\n    pass\n", encoding="utf-8")
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
            return f"CLI returned {completed.returncode}"
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


def _check_subdirectory_path(git: str) -> str | None:
    with TemporaryDirectory(prefix="scope-markers-diff-subdirectory-") as raw:
        root = Path(raw)
        (root / "src").mkdir()
        tests = root / "tests"
        tests.mkdir()
        (tests / "example.py").write_text(
            "def example():\n    pass\n", encoding="utf-8"
        )
        initialized = subprocess.run(
            [git, "init", "--quiet"], cwd=root, check=False, capture_output=True
        )
        if initialized.returncode:
            return initialized.stderr.decode(errors="replace")
        ####
        arguments = ("../tests/example.py", str(tests / "example.py"))
        for index, argument in enumerate(arguments):
            completed = subprocess.run(
                [sys.executable, "-m", "scope_markers", "--diff", argument],
                cwd=root / "src",
                check=False,
                capture_output=True,
            )
            if completed.returncode != 1:
                return f"CLI returned {completed.returncode} for {argument}"
            ####
            expected_headers = (
                b"--- a/tests/example.py\n",
                b"+++ b/tests/example.py\n",
            )
            if any(header not in completed.stdout for header in expected_headers):
                return f"unexpected diff labels for {argument}"
            ####
            unsafe_prefixes = (b"a/../", b"b/../", b"a//", b"b//")
            if any(prefix in completed.stdout for prefix in unsafe_prefixes):
                return f"unsafe diff labels for {argument}"
            ####
            patch = root / f"change-{index}.patch"
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
    ####
    return None
####


def _check_multiple_file_output(git: str) -> str | None:
    with TemporaryDirectory(prefix="scope-markers-diff-multiple-") as raw:
        root = Path(raw)
        utf8 = root / "utf8.py"
        cp1252 = root / "cp1252.py"
        clean = root / "clean.py"
        utf8.write_bytes(b"# coding: utf-8\ndef example():\n    value = 'h\xc3\xa9llo'\n")
        cp1252.write_bytes(
            b"# coding: cp1252\ndef example():\n    value = 'h\xe9llo'\n"
        )
        clean.write_text("value = 1\n", encoding="utf-8")
        initialized = subprocess.run(
            [git, "init", "--quiet"], cwd=root, check=False, capture_output=True
        )
        if initialized.returncode:
            return initialized.stderr.decode(errors="replace")
        ####
        expected: dict[Path, bytes] = {}
        for path in (utf8, cp1252):
            inspection = inspect_file(path)
            expected[path] = inspection.formatted.encode(inspection.encoding)
        ####
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "scope_markers",
                "--diff",
                str(utf8),
                str(cp1252),
                str(clean),
            ],
            cwd=root,
            check=False,
            capture_output=True,
        )
        if completed.returncode != 1:
            return f"CLI returned {completed.returncode}"
        ####
        if b"scope markers" in completed.stdout:
            return "status text leaked into multi-file patch output"
        ####
        patch = root / "change.patch"
        patch.write_bytes(completed.stdout)
        checked = subprocess.run(
            [git, "-c", "core.autocrlf=false", "apply", "--check", str(patch)],
            cwd=root,
            check=False,
            capture_output=True,
        )
        if checked.returncode:
            return checked.stderr.decode(errors="replace")
        ####
        applied = subprocess.run(
            [git, "-c", "core.autocrlf=false", "apply", str(patch)],
            cwd=root,
            check=False,
            capture_output=True,
        )
        if applied.returncode:
            return applied.stderr.decode(errors="replace")
        ####
        for path, data in expected.items():
            if path.read_bytes() != data:
                return f"git apply produced unexpected bytes for {path.name}"
            ####
        ####
    ####
    return None
####


def _check_autocrlf_modes(git: str) -> str | None:
    newline_cases = (
        ("lf", b"def example():\n    pass\n"),
        ("crlf", b"def example():\r\n    pass\r\n"),
    )
    for mode in AUTOCRLF_MODES:
        for name, source in newline_cases:
            with TemporaryDirectory(prefix=f"scope-markers-autocrlf-{mode}-{name}-") as raw:
                root = Path(raw)
                path = root / "example.py"
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
                    return f"CLI returned {completed.returncode} for autocrlf={mode}"
                ####
                patch = root / "change.patch"
                patch.write_bytes(completed.stdout)
                git_apply = [git, "-c", f"core.autocrlf={mode}", "apply"]
                checked = subprocess.run(
                    [*git_apply, "--check", str(patch)],
                    cwd=root,
                    check=False,
                    capture_output=True,
                )
                if checked.returncode:
                    return (
                        f"git apply --check failed for autocrlf={mode}, "
                        f"newline={name}: {checked.stderr.decode(errors='replace')}"
                    )
                ####
                applied = subprocess.run(
                    [*git_apply, str(patch)],
                    cwd=root,
                    check=False,
                    capture_output=True,
                )
                if applied.returncode:
                    return (
                        f"git apply failed for autocrlf={mode}, "
                        f"newline={name}: {applied.stderr.decode(errors='replace')}"
                    )
                ####
                if inspect_file(path).changed:
                    return f"result is not clean for autocrlf={mode}, newline={name}"
                ####
            ####
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
    failure = _check_subdirectory_path(git)
    if failure is not None:
        print(f"diff contract failed for subdirectory path: {failure}", file=sys.stderr)
        return 1
    ####
    failure = _check_multiple_file_output(git)
    if failure is not None:
        print(f"diff contract failed for multiple files: {failure}", file=sys.stderr)
        return 1
    ####
    failure = _check_autocrlf_modes(git)
    if failure is not None:
        print(f"diff contract failed for autocrlf modes: {failure}", file=sys.stderr)
        return 1
    ####
    failure = _check_bare_cr()
    if failure is not None:
        print(f"diff contract failed for bare-CR input: {failure}", file=sys.stderr)
        return 1
    ####
    failure = _check_newline_filename(git)
    if failure is not None:
        print(f"diff contract failed for newline filename: {failure}", file=sys.stderr)
        return 1
    ####
    print(
        f"diff contract passed ({len(DIFF_CASES)} content cases, "
        "2 nested-path cases, 1 multi-file case, 6 autocrlf cases, "
        "bare-CR rejection, and pathological filename coverage where supported)"
    )
    return 0
####


if __name__ == "__main__":
    raise SystemExit(main())
####

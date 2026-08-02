"""Smoke-test Black on source with project-specific markers removed."""

from __future__ import annotations

import subprocess
import sys
import tokenize
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOTS = (ROOT / "src", ROOT / "scripts", ROOT / "tests")
MARKERS = {"##", "####"}

def _without_standalone_markers(source: str) -> str:
    lines = source.splitlines(keepends=True)
    marker_rows: set[int] = set()
    for token in tokenize.generate_tokens(StringIO(source).readline):
        if token.type != tokenize.COMMENT or token.string.strip() not in MARKERS:
            continue
        ####
        row, column = token.start
        line = lines[row - 1]
        if not line[:column].strip() and not line[token.end[1]:].strip():
            marker_rows.add(row - 1)
        ####
    ####
    return "".join(line for index, line in enumerate(lines) if index not in marker_rows)
####


def _copy_unmarked_sources(destination: Path) -> None:
    for source_root in PYTHON_ROOTS:
        target_root = destination / source_root.relative_to(ROOT)
        for source in source_root.rglob("*.py"):
            relative = source.relative_to(source_root)
            target = target_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            with tokenize.open(source) as stream:
                contents = _without_standalone_markers(stream.read())
                encoding = stream.encoding
            ####
            target.write_text(contents, encoding=encoding, newline="")
        ####
    ####
####


def main() -> int:
    """Verify Black can format and recheck a marker-free temporary source tree."""
    with TemporaryDirectory(prefix="scope-markers-black-") as directory:
        destination = Path(directory)
        _copy_unmarked_sources(destination)
        format_command = [
            sys.executable,
            "-m",
            "black",
            "--quiet",
            str(destination / "src"),
            str(destination / "scripts"),
            str(destination / "tests"),
        ]
        formatted = subprocess.run(format_command, cwd=ROOT, check=False)
        if formatted.returncode:
            return formatted.returncode
        ####
        check_command = [*format_command, "--check"]
        return subprocess.run(check_command, cwd=ROOT, check=False).returncode
    ####
####


if __name__ == "__main__":
    raise SystemExit(main())
####

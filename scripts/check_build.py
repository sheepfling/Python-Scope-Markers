"""Build a wheel into an isolated temporary output directory."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]

def main() -> int:
    """Verify wheel packaging without reusing stale distribution artifacts."""
    with TemporaryDirectory(prefix="scope-markers-wheel-") as output:
        return subprocess.run(
            [sys.executable, "-m", "build", "--wheel", "--outdir", output],
            cwd=ROOT,
            check=False,
        ).returncode
    ####
####


if __name__ == "__main__":
    raise SystemExit(main())
####

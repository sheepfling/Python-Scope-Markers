"""Shared source decoding, line handling, and atomic file writes."""

from __future__ import annotations

import os
import stat
import tempfile
import tokenize
from collections.abc import Callable, Iterator
from contextlib import suppress
from io import StringIO
from pathlib import Path


def read_source(path: Path) -> tuple[str, str]:
    """Read one source file while preserving its declared encoding."""
    data = path.read_bytes()
    encoding, _ = tokenize.detect_encoding(_byte_line_reader(data))
    return data.decode(encoding), encoding
####


def _physical_byte_lines(data: bytes) -> Iterator[bytes]:
    """Yield byte records split only on CR, LF, and CRLF boundaries."""
    index = 0
    while index < len(data):
        start = index
        while index < len(data) and data[index] not in (ord("\r"), ord("\n")):
            index += 1
        ####
        if index == len(data):
            yield data[start:]
            return
        ####
        index += 1
        if data[index - 1] == ord("\r") and index < len(data) and data[index] == ord("\n"):
            index += 1
        ####
        yield data[start:index]
    ####
####


def _byte_line_reader(data: bytes) -> Callable[[], bytes]:
    """Return LF-normalized physical records for ``tokenize.detect_encoding``."""
    lines = iter(_physical_byte_lines(data))

    def readline() -> bytes:
        line = next(lines, b"")
        if line.endswith(b"\r\n"):
            return line[:-2] + b"\n"
        ####
        if line.endswith(b"\r"):
            return line[:-1] + b"\n"
        ####
        return line
    ####

    return readline
####


def physical_lines(source: str) -> list[str]:
    """Split only on Python-supported CR, LF, and CRLF line boundaries."""
    return StringIO(source, newline="").readlines()
####


def write_atomic(path: Path, data: bytes) -> None:
    """Replace a file atomically while preserving executable permission bits."""
    target = path.resolve(strict=True) if path.is_symlink() else path
    mode = stat.S_IMODE(target.stat().st_mode)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        suffix=".scope-markers.tmp",
        dir=target.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        ####
        os.chmod(temporary, mode)
        os.replace(temporary, target)
    finally:
        with suppress(OSError):
            temporary.unlink(missing_ok=True)
        ####
    ####
####

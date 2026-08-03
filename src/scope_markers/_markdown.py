"""Format Python code fences embedded in Markdown documents."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from ._implementation import (
    FILE_PROCESSING_ERRORS,
    FileInspection,
    _error_message,  # pyright: ignore[reportPrivateUsage]
    _physical_lines,  # pyright: ignore[reportPrivateUsage]
    _read_source,  # pyright: ignore[reportPrivateUsage]
    _write_atomic,  # pyright: ignore[reportPrivateUsage]
    format_source,
    strip_markers,
)
from ._policy import MarkerPolicy

PYTHON_FENCE_LANGUAGES = frozenset({"py", "python", "python3"})
_FENCE_PATTERN = re.compile(r"^( {0,3})([`~]{3,})(.*)$")
_PYTHON_IGNORE_PATTERN = re.compile(
    r"^#\s*(?:no-scope-markers|scope-markers\s*[:=]\s*(?:off|ignore|false))\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class _FenceBlock:
    """One complete Markdown fence span in the original line sequence."""

    opening_index: int
    closing_index: int
    indentation: str
    fence: str
    info: str
####


def _fence_parts(line: str) -> tuple[str, str, str] | None:
    body = line.rstrip("\r\n")
    match = _FENCE_PATTERN.match(body)
    if match is None:
        return None
    ####
    fence = match.group(2)
    if len(set(fence)) != 1 or (fence[0] == "`" and "`" in match.group(3)):
        return None
    ####
    return match.group(1), fence, match.group(3).strip()
####


def _is_fence_closing(line: str, fence: str) -> bool:
    body = line.rstrip("\r\n")
    indentation_length = len(body) - len(body.lstrip(" "))
    if indentation_length > 3:
        return False
    ####
    remainder = body[indentation_length:]
    if not remainder.startswith(fence[0] * len(fence)):
        return False
    ####
    return not remainder[len(fence):].strip(fence[0] + " \t")
####


def _fence_blocks(lines: Sequence[str]) -> tuple[_FenceBlock, ...]:
    """Collect complete, non-nested fence spans without mutating ``lines``."""
    blocks: list[_FenceBlock] = []
    index = 0
    while index < len(lines):
        parts = _fence_parts(lines[index])
        if parts is None:
            index += 1
            continue
        ####
        indentation, fence, info = parts
        closing_index = index + 1
        while closing_index < len(lines) and not _is_fence_closing(
                lines[closing_index], fence
        ):
            closing_index += 1
        ####
        if closing_index >= len(lines):
            break
        ####
        blocks.append(
            _FenceBlock(
                opening_index=index,
                closing_index=closing_index,
                indentation=indentation,
                fence=fence,
                info=info,
            )
        )
        index = closing_index + 1
    ####
    return tuple(blocks)
####


def _has_python_ignore_directive(lines: Sequence[str]) -> bool:
    """Return whether the first content line opts a Python fence out."""
    for line in lines:
        content = line.strip(" \t\r\n")
        if content:
            return _PYTHON_IGNORE_PATTERN.fullmatch(content) is not None
        ####
    ####
    return False
####


def _remove_fence_indentation(lines: Sequence[str], indentation: str) -> tuple[str, ...]:
    if not indentation:
        return tuple(lines)
    ####
    return tuple(
        line[min(len(indentation), len(line) - len(line.lstrip(" "))):]
        for line in lines
    )
####


def _restore_fence_indentation(
        lines: Sequence[str], original_lines: Sequence[str], indentation: str
) -> tuple[str, ...]:
    if not indentation:
        return tuple(lines)
    ####
    had_indentation = any(
        line.startswith(indentation) and line.strip("\r\n") for line in original_lines
    )
    if not had_indentation:
        return tuple(lines)
    ####
    restored: list[str] = []
    for index, line in enumerate(lines):
        has_original_indentation = (
            index < len(original_lines)
            and original_lines[index].startswith(indentation)
        )
        if line.strip("\r\n") or has_original_indentation:
            restored.append(indentation + line)
        else:
            restored.append(line)
        ####
    ####
    return tuple(restored)
####


def format_markdown_source(
        source: str,
        *,
        filename: str = "<unknown>",
        mark_stubs: bool = False,
        indent_width: int | None = None,
        strip: bool = False,
        policy: MarkerPolicy | None = None,
) -> str:
    """Format Python fences in Markdown while preserving surrounding text."""
    lines = _physical_lines(source)
    formatted_lines = list(lines)
    for block in reversed(_fence_blocks(lines)):
        language = block.info.split(maxsplit=1)
        if not language or language[0].casefold() not in PYTHON_FENCE_LANGUAGES:
            continue
        ####
        original_payload = tuple(
            lines[block.opening_index + 1:block.closing_index]
        )
        if _has_python_ignore_directive(
                _remove_fence_indentation(original_payload, block.indentation)
        ):
            continue
        ####
        payload = "".join(
            _remove_fence_indentation(original_payload, block.indentation)
        )
        if strip:
            formatted_payload = strip_markers(payload)
        else:
            formatted_payload = format_source(
                payload,
                filename=f"{filename}:{block.opening_index + 1}",
                mark_stubs=mark_stubs,
                indent_width=indent_width,
                policy=policy,
            )
        ####
        formatted_payload_lines = _physical_lines(formatted_payload)
        restored = _restore_fence_indentation(
            formatted_payload_lines, original_payload, block.indentation
        )
        formatted_lines[block.opening_index + 1:block.closing_index] = restored
    ####
    return "".join(formatted_lines)
####


def inspect_markdown_file(
        path: Path,
        *,
        mark_stubs: bool = False,
        indent_width: int | None = None,
        strip: bool = False,
        policy: MarkerPolicy | None = None,
) -> FileInspection:
    """Read and canonicalize Python fences in one Markdown file."""
    source, encoding = _read_source(path)
    formatted = format_markdown_source(
        source,
        filename=str(path),
        mark_stubs=mark_stubs,
        indent_width=indent_width,
        strip=strip,
        policy=policy,
    )
    return FileInspection(path=path, source=source, formatted=formatted, encoding=encoding)
####


def process_markdown_file(
        path: Path,
        *,
        fix: bool,
        mark_stubs: bool = False,
        indent_width: int | None = None,
        strip: bool = False,
        policy: MarkerPolicy | None = None,
) -> tuple[bool, str | None]:
    """Check or fix one Markdown file and return ``(changed, error)``."""
    try:
        inspection = inspect_markdown_file(
            path,
            mark_stubs=mark_stubs,
            indent_width=indent_width,
            strip=strip,
            policy=policy,
        )
        if inspection.changed and fix:
            _write_atomic(path, inspection.formatted.encode(inspection.encoding))
        ####
    except FILE_PROCESSING_ERRORS as error:
        return False, _error_message(path, error)
    ####
    return inspection.changed, None
####

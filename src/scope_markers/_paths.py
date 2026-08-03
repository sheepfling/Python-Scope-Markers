"""Safe rendering helpers for user-supplied filesystem paths."""

from __future__ import annotations

import unicodedata
from pathlib import Path


def display_path(path: Path) -> str:
    """Render a path without allowing control characters to forge output."""
    rendered: list[str] = []
    for character in str(path):
        category = unicodedata.category(character)
        if category not in {"Cc", "Cf", "Zl", "Zp"}:
            rendered.append(character)
            continue
        ####
        escapes = {
            "\a": r"\a",
            "\b": r"\b",
            "\t": r"\t",
            "\n": r"\n",
            "\v": r"\v",
            "\f": r"\f",
            "\r": r"\r",
        }
        rendered.append(escapes.get(character, f"\\u{ord(character):04x}"))
    ####
    return "".join(rendered)
####

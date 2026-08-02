"""Contract tests for semantic indentation normalization."""

from __future__ import annotations

import pytest

from scope_markers.api import format_source

INLINE_SUITE_COMMENT_CASES = (
    pytest.param(
        "if enabled: pass\n    # attached\nnext_value = 1\n",
        "  # attached",
        id="if",
    ),
    pytest.param(
        "def work() -> None: pass\n    # attached\nnext_value = 1\n",
        "  # attached",
        id="function",
    ),
    pytest.param(
        "class Example: pass\n    # attached\nnext_value = 1\n",
        "  # attached",
        id="class",
    ),
    pytest.param(
        "for item in (): pass\n    # attached\nnext_value = 1\n",
        "  # attached",
        id="for",
    ),
    pytest.param(
        "while False: pass\n    # attached\nnext_value = 1\n",
        "  # attached",
        id="while",
    ),
    pytest.param(
        "with manager: pass\n    # attached\nnext_value = 1\n",
        "  # attached",
        id="with",
    ),
    pytest.param(
        "if first: pass\nelif second: pass\n    # attached\nnext_value = 1\n",
        "  # attached",
        id="elif",
    ),
    pytest.param(
        "if first: pass\nelse: pass\n    # attached\nnext_value = 1\n",
        "  # attached",
        id="else",
    ),
    pytest.param(
        "try: pass\nexcept ValueError: pass\n    # attached\nnext_value = 1\n",
        "  # attached",
        id="except",
    ),
    pytest.param(
        "try: pass\nexcept* ValueError: pass\n    # attached\nnext_value = 1\n",
        "  # attached",
        id="except-star",
    ),
    pytest.param(
        "try: pass\nfinally: pass\n    # attached\nnext_value = 1\n",
        "  # attached",
        id="finally",
    ),
    pytest.param(
        "async def worker():\n  async for item in items: pass\n    # attached\n",
        "    # attached",
        id="async-for",
    ),
    pytest.param(
        "async def worker():\n  async with manager: pass\n    # attached\n",
        "    # attached",
        id="async-with",
    ),
    pytest.param(
        "match value:\n  case 1: pass\n    # attached\n  case _: pass\n",
        "    # attached",
        id="case",
    ),
)

@pytest.mark.parametrize("newline", ("\n", "\r\n", "\r"))
@pytest.mark.parametrize(
    ("source", "expected_comment"), INLINE_SUITE_COMMENT_CASES
)
def test_inline_suite_comments_have_semantic_depth(
        source: str, expected_comment: str, newline: str
) -> None:
    formatted = format_source(source.replace("\n", newline), indent_width=2)

    comment = next(line for line in formatted.splitlines() if "# attached" in line)
    assert comment == expected_comment
    assert format_source(formatted, indent_width=2) == formatted
####

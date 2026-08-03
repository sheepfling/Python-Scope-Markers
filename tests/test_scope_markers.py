from __future__ import annotations

import os
import re
import stat
import subprocess
import sys
from collections.abc import Callable
from contextlib import suppress
from importlib.metadata import entry_points
from importlib.metadata import version as installed_version
from pathlib import Path
from typing import cast

import pytest

import scope_markers as package
from scope_markers import _paths, api, cli
from scripts import check_black, check_diff, check_rumdl, ci

# Literal ``####`` values intentionally verify the formatter's defining output.
scope_markers = api

def test_nested_scopes_are_closed_inside_out() -> None:
    source = (
        "class Example:\n"
        "    def method(self, value: int) -> int:\n"
        "        if value > 0:\n"
        "            return value\n"
        "        else:\n"
        "            return -value\n"
    )

    formatted = scope_markers.format_source(source)

    assert formatted == (
        "class Example:\n"
        "    def method(self, value: int) -> int:\n"
        "        if value > 0:\n"
        "            return value\n"
        "        else:\n"
        "            return -value\n"
        "        ####\n"
        "    ####\n"
        "####\n"
    )
    assert scope_markers.format_source(formatted) == formatted
####


@pytest.mark.parametrize("newline", ("\n", "\r\n", "\r"))
def test_indent_width_normalizes_blocks_and_regenerates_markers(newline: str) -> None:
    source = (
        "if outer:\n"
        "    # The nested scope follows.\n"
        "    if inner:\n"
        "        pass\n"
        "    ####\n"
        "####\n"
    ).replace("\n", newline)

    assert scope_markers.format_source(source, indent_width=2) == (
        "if outer:\n"
        "  # The nested scope follows.\n"
        "  if inner:\n"
        "    pass\n"
        "  ####\n"
        "####\n"
    ).replace("\n", newline)
####


@pytest.mark.parametrize(("existing_marker", "expected_marker"), (("", "####"), ("##\n", "##")))
def test_indent_width_does_not_mark_parenthesized_continuations(
        existing_marker: str, expected_marker: str
) -> None:
    source = (
        "if ready:\n"
        "    values = (\n"
        "        first\n"
        "        + second\n"
        "    )\n"
        f"{existing_marker}"
    )

    formatted = scope_markers.format_source(source, indent_width=2)

    assert formatted == (
        "if ready:\n"
        "  values = (\n"
        "        first\n"
        "        + second\n"
        "    )\n"
        f"{expected_marker}\n"
    )
    assert formatted.count(expected_marker) == 1
    assert scope_markers.format_source(formatted, indent_width=2) == formatted
####


def test_indent_width_preserves_continuation_alignment_and_converts_block_tabs() -> None:
    source = (
        "if ready:\n"
        "\tvalue = (\n"
        "        first\n"
        "        + second\n"
        "    )\n"
    )

    assert scope_markers.format_source(source, indent_width=2) == (
        "if ready:\n"
        "  value = (\n"
        "        first\n"
        "        + second\n"
        "    )\n"
        "####\n"
    )
####


def test_indent_width_preserves_if_elif_chain_boundaries() -> None:
    source = "if first:\n    pass\nelif second:\n    pass\n"

    assert scope_markers.format_source(source, indent_width=2) == (
        "if first:\n"
        "  pass\n"
        "elif second:\n"
        "  pass\n"
        "####\n"
    )
####


@pytest.mark.parametrize(("source_width", "target_width"), ((2, 4), (4, 2)))
def test_indent_width_converts_between_two_and_four_spaces(
        source_width: int, target_width: int
) -> None:
    source_indent = " " * source_width
    target_indent = " " * target_width
    source = (
        "class Example:\n"
        f"{source_indent}def method() -> None:\n"
        f"{source_indent * 2}pass\n"
    )

    formatted = scope_markers.format_source(source, indent_width=target_width)

    assert formatted == (
        "class Example:\n"
        f"{target_indent}def method() -> None:\n"
        f"{target_indent * 2}pass\n"
        f"{target_indent}####\n"
        "####\n"
    )
    assert scope_markers.format_source(formatted, indent_width=target_width) == formatted
####


@pytest.mark.parametrize("target_width", (2, 4))
def test_indent_width_normalizes_an_adversarial_valid_mixed_indentation_file(
        target_width: int,
) -> None:
    source = (
        "if outer:\n"
        "\t# The chain intentionally mixes tab, two-space, and four-space levels.\n"
        "\tif first:\n"
        "\t  pass\n"
        "\telif second:\n"
        "\t    pass\n"
        "\telse:\n"
        "\t\tpass\n"
    )
    indent = " " * target_width

    formatted = scope_markers.format_source(source, indent_width=target_width)

    assert formatted == (
        "if outer:\n"
        f"{indent}# The chain intentionally mixes tab, two-space, and four-space levels.\n"
        f"{indent}if first:\n"
        f"{indent * 2}pass\n"
        f"{indent}elif second:\n"
        f"{indent * 2}pass\n"
        f"{indent}else:\n"
        f"{indent * 2}pass\n"
        f"{indent}####\n"
        "####\n"
    )
    assert "\t" not in formatted
    assert scope_markers.format_source(formatted, indent_width=target_width) == formatted
####


def test_indent_width_handles_mixed_indentation_with_continuations_and_match_cases() -> None:
    source = (
        "def outer(\n"
        "        value: int,\n"
        ") -> int:\n"
        "\t# The physical widths below are deliberately irregular but valid.\n"
        "\ttry:\n"
        "\t  match value:\n"
        "\t    case 1:\n"
        "\t      return value\n"
        "\t    case _:\n"
        "\t        return 0\n"
        "\texcept ValueError:\n"
        "\t\treturn -1\n"
    )

    assert scope_markers.format_source(source, indent_width=2) == (
        "def outer(\n"
        "        value: int,\n"
        ") -> int:\n"
        "  # The physical widths below are deliberately irregular but valid.\n"
        "  try:\n"
        "    match value:\n"
        "      case 1:\n"
        "        return value\n"
        "      case _:\n"
        "        return 0\n"
        "      ####\n"
        "    ####\n"
        "  except ValueError:\n"
        "    return -1\n"
        "  ####\n"
        "####\n"
    )
####


@pytest.mark.parametrize("newline", ("\n", "\r\n", "\r"))
def test_indent_width_normalizes_comments_after_one_line_suites(newline: str) -> None:
    source = (
        "if enabled: pass\n"
        "    # Attached to the one-line suite.\n"
        "next_value = 1\n"
    ).replace("\n", newline)

    assert scope_markers.format_source(source, indent_width=2) == (
        "if enabled: pass\n"
        "  # Attached to the one-line suite.\n"
        "####\n"
        "next_value = 1\n"
    ).replace("\n", newline)
####


def test_inline_comment_depth_overrides_a_matching_nested_prefix() -> None:
    source = (
        "if inline: pass\n"
        "    # Attached to the inline suite, not the later nested block.\n"
        "if outer:\n"
        "  if inner:\n"
        "    pass\n"
    )

    formatted = scope_markers.format_source(source, indent_width=2)

    assert formatted.startswith(
        "if inline: pass\n"
        "  # Attached to the inline suite, not the later nested block.\n"
        "####\n"
    )
    assert scope_markers.format_source(formatted, indent_width=2) == formatted
####


def test_indent_width_normalizes_comments_after_inline_clause_headers() -> None:
    source = (
        "try: pass\n"
        "except ValueError: pass\n"
        "    # Attached to the except suite.\n"
        "next_value = 1\n"
    )

    assert scope_markers.format_source(source, indent_width=2) == (
        "try: pass\n"
        "except ValueError: pass\n"
        "  # Attached to the except suite.\n"
        "####\n"
        "next_value = 1\n"
    )
####


@pytest.mark.parametrize("newline", ("\n", "\r\n", "\r"))
def test_indent_width_normalizes_comments_after_multiline_inline_headers(
        newline: str,
) -> None:
    source = (
        "if (\n"
        "    condition\n"
        "): pass\n"
        "    # Attached to the multiline inline suite.\n"
        "next_value = 1\n"
    ).replace("\n", newline)

    assert scope_markers.format_source(source, indent_width=2) == (
        "if (\n"
        "    condition\n"
        "): pass\n"
        "  # Attached to the multiline inline suite.\n"
        "####\n"
        "next_value = 1\n"
    ).replace("\n", newline)
####


@pytest.mark.parametrize("newline", ("\n", "\r\n", "\r"))
def test_indent_width_preserves_nested_multiline_docstring_content(
        newline: str,
) -> None:
    source = (
        "class Example:\n"
        '    """Class docs.\n'
        "\n"
        "    # Literal comment text.\n"
        "    ####\n"
        "    \\tPreserve this tab.\n"
        '    """\n'
        "    def method(self):\n"
        '        r"""Method docs.\n'
        "\n"
        "        # Not a source comment.\n"
        '        """\n'
        "        if ready:\n"
        "            pass\n"
    ).replace("\n", newline)

    formatted = scope_markers.format_source(source, indent_width=2)

    assert formatted == (
        "class Example:\n"
        '  """Class docs.\n'
        "\n"
        "    # Literal comment text.\n"
        "    ####\n"
        "    \\tPreserve this tab.\n"
        '    """\n'
        "  def method(self):\n"
        '    r"""Method docs.\n'
        "\n"
        "        # Not a source comment.\n"
        '        """\n'
        "    if ready:\n"
        "      pass\n"
        "    ####\n"
        "  ####\n"
        "####\n"
    ).replace("\n", newline)
    assert scope_markers.format_source(formatted, indent_width=2) == formatted
####


def test_indent_width_normalizes_comments_after_inline_match_cases() -> None:
    source = (
        "match value:\n"
        "  case 1: pass\n"
        "    # Attached to the case suite.\n"
        "  case _: pass\n"
    )

    assert scope_markers.format_source(source, indent_width=2) == (
        "match value:\n"
        "  case 1: pass\n"
        "    # Attached to the case suite.\n"
        "  case _: pass\n"
        "  ####\n"
        "####\n"
    )
####


def test_cli_indent_width_refuses_ambiguous_mixed_indentation(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "ambiguous.py"
    source = "if outer:\n\tpass\n        pass\n"
    path.write_text(source, encoding="utf-8")

    assert cli.main(["--indent-width", "2", "--fix", "--quiet", str(path)]) == 2
    assert path.read_text(encoding="utf-8") == source
    assert "indent" in capsys.readouterr().err.casefold()
####


def test_indent_width_requires_a_positive_value() -> None:
    with pytest.raises(scope_markers.ScopeMarkersError, match="indent_width must be"):
        scope_markers.format_source("pass\n", indent_width=0)
    ####
####


@pytest.mark.parametrize("newline", ("\n", "\r\n", "\r"))
def test_all_compound_statement_families_are_supported(newline: str) -> None:
    source = (
        "async def worker(items: object) -> None:\n"
        "    async for item in items:\n"
        "        async with item:\n"
        "            while item:\n"
        "                break\n"
        "    for item in []:\n"
        "        pass\n"
        "    with open('x') as stream:\n"
        "        pass\n"
        "    try:\n"
        "        match item:\n"
        "            case 1:\n"
        "                pass\n"
        "            case _:\n"
        "                pass\n"
        "    except* OSError:\n"
        "        pass\n"
        "class Example:\n"
        "    pass\n"
        "if ready:\n"
        "    pass\n"
    ).replace("\n", newline)

    formatted = scope_markers.format_source(source)

    assert formatted.count("####") == 11
    assert scope_markers.format_source(formatted) == formatted
####


def test_elif_else_loop_else_and_try_clauses_get_one_marker_each() -> None:
    source = (
        "if value > 0:\n"
        "    pass\n"
        "elif value < 0:\n"
        "    pass\n"
        "else:\n"
        "    pass\n"
        "for item in items:\n"
        "    pass\n"
        "else:\n"
        "    pass\n"
        "while ready:\n"
        "    break\n"
        "else:\n"
        "    pass\n"
        "try:\n"
        "    pass\n"
        "except OSError:\n"
        "    pass\n"
        "else:\n"
        "    pass\n"
        "finally:\n"
        "    pass\n"
    )

    assert scope_markers.format_source(source).count("####") == 4
####


def test_match_cases_and_match_statement_are_closed_separately() -> None:
    source = (
        "match value:\n"
        "    case 1:\n"
        "        pass\n"
        "    case 2 if ready:\n"
        "        pass\n"
        "    case _:\n"
        "        pass\n"
    )

    formatted = scope_markers.format_source(source)

    assert formatted == (
        "match value:\n"
        "    case 1:\n"
        "        pass\n"
        "    case 2 if ready:\n"
        "        pass\n"
        "    case _:\n"
        "        pass\n"
        "    ####\n"
        "####\n"
    )
    assert scope_markers.format_source(formatted) == formatted
####


def test_multiline_match_case_marker_uses_case_header_indentation() -> None:
    source = (
        "match value:\n"
        "    case (\n"
        "        1\n"
        "    ):\n"
        "        pass\n"
    )

    assert scope_markers.format_source(source) == (
        "match value:\n"
        "    case (\n"
        "        1\n"
        "    ):\n"
        "        pass\n"
        "    ####\n"
        "####\n"
    )
####


def test_multiline_match_case_capture_named_case_uses_header_indentation() -> None:
    source = (
        "match value:\n"
        "    case (\n"
        "        case\n"
        "    ):\n"
        "        pass\n"
    )

    assert scope_markers.format_source(source) == (
        "match value:\n"
        "    case (\n"
        "        case\n"
        "    ):\n"
        "        pass\n"
        "    ####\n"
        "####\n"
    )
####


def test_explicit_match_case_continuation_uses_header_indentation() -> None:
    source = (
        "match value:\n"
        "    case \\\n"
        "        case:\n"
        "        pass\n"
    )

    assert scope_markers.format_source(source) == (
        "match value:\n"
        "    case \\\n"
        "        case:\n"
        "        pass\n"
        "    ####\n"
        "####\n"
    )
####


@pytest.mark.parametrize("newline", ("\n", "\r\n", "\r"))
def test_match_case_header_after_comment_is_detected(newline: str) -> None:
    source = newline.join(
        (
            "match value:",
            "    # Cases follow this explanation.",
            "    case 1:",
            "        pass",
        )
    ) + newline

    assert scope_markers.format_source(source).endswith(
        f"    case 1:{newline}"
        f"        pass{newline}"
        f"    ####{newline}"
        f"####{newline}"
    )
####


def test_cli_fix_accepts_bare_cr_match_statements(tmp_path: Path) -> None:
    path = tmp_path / "bare-cr-match.py"
    path.write_bytes(b"match value:\r    case 1:\r        pass\r")

    assert cli.main(["--fix", "--quiet", str(path)]) == 0
    assert path.read_bytes() == (
        b"match value:\r    case 1:\r        pass\r    ####\r####\r"
    )
####


def test_cli_fix_detects_a_bare_cr_encoding_cookie(tmp_path: Path) -> None:
    path = tmp_path / "bare-cr-cp1252.py"
    path.write_bytes(
        b"# coding: cp1252\r"
        b"match value:\r"
        b"    case 1:\r"
        b"        label = '\xe9'\r"
    )

    assert cli.main(["--fix", "--quiet", str(path)]) == 0
    assert path.read_bytes() == (
        b"# coding: cp1252\r"
        b"match value:\r"
        b"    case 1:\r"
        b"        label = '\xe9'\r"
        b"    ####\r"
        b"####\r"
    )
####


@pytest.mark.parametrize("newline", ("\n", "\r\n", "\r"))
def test_standalone_markers_are_recognized_with_all_newline_conventions(
        newline: str,
) -> None:
    source = (
        f"def example() -> None:{newline}"
        f"    pass{newline}"
        f"####{newline}"
    )

    assert scope_markers.format_source(source) == source
####


@pytest.mark.parametrize(
    "source",
    (
            "if first:\n    pass\n\felif second:\n    pass\n",
            "\fif first:\n    pass\nelif second:\n    pass\n",
    ),
)
def test_elif_chain_uses_effective_form_feed_indentation(source: str) -> None:
    formatted = scope_markers.format_source(source)

    assert formatted.count("####") == 1
    assert scope_markers.format_source(formatted) == formatted
####


def test_nested_match_case_header_after_comment_uses_inner_indentation() -> None:
    source = (
        "match outer:\n"
        "    case 1:\n"
        "        match inner:\n"
        "            # Inner cases follow this explanation.\n"
        "            case 2:\n"
        "                pass\n"
    )

    assert scope_markers.format_source(source).endswith(
        "            case 2:\n"
        "                pass\n"
        "            ####\n"
        "        ####\n"
        "    ####\n"
        "####\n"
    )
####


def test_large_match_table_uses_stable_case_header_lookup() -> None:
    source = "match value:\n" + "".join(
        f"    case {index}:\n        pass\n" for index in range(1000)
    )

    formatted = scope_markers.format_source(source)

    assert formatted.count("####") == 2
    assert scope_markers.format_source(formatted) == formatted
####


def test_long_elif_chain_has_one_boundary_and_is_idempotent() -> None:
    source = "if value == 0:\n    pass\n" + "".join(
        f"elif value == {index}:\n    pass\n" for index in range(1, 1000)
    ) + "else:\n    pass\n"

    formatted = scope_markers.format_source(source)

    assert formatted.count("####") == 1
    assert scope_markers.format_source(formatted) == formatted
####


def test_many_independent_compound_statements_are_stable() -> None:
    source = "".join(
        f"def function_{index}() -> int:\n    return {index}\n"
        for index in range(1000)
    )

    formatted = scope_markers.format_source(source)

    assert formatted.count("####") == 1000
    assert scope_markers.format_source(formatted) == formatted
####


def test_deeply_nested_if_scopes_are_stable() -> None:
    # CPython rejects indentation nesting beyond 100 levels.
    depth = 90
    source = "".join(f"{'    ' * level}if value:\n" for level in range(depth))
    source += f"{'    ' * depth}pass\n"

    formatted = scope_markers.format_source(source)

    assert formatted.count("####") == depth
    assert scope_markers.format_source(formatted) == formatted
####


def test_deeply_nested_classes_and_functions_are_stable() -> None:
    # Alternate class and function suites while staying below CPython's
    # indentation-depth limit.
    pairs = 40
    source = "".join(
        f"{'    ' * (2 * level)}class Level{level}:\n"
        f"{'    ' * (2 * level + 1)}def function_{level}():\n"
        for level in range(pairs)
    )
    source += f"{'    ' * (2 * pairs)}pass\n"

    formatted = scope_markers.format_source(source)

    assert formatted.count("####") == pairs * 2
    assert scope_markers.format_source(formatted) == formatted
####


@pytest.mark.parametrize(
    "case_header",
    ("case[1]:", 'case{"key": value}:', "case-1:"),
    ids=("sequence-pattern", "mapping-pattern", "negative-pattern"),
)
def test_punctuation_after_case_soft_keyword_is_supported(case_header: str) -> None:
    source = (
        "match value:\n"
        f"    {case_header}\n"
        "        pass\n"
    )

    formatted = scope_markers.format_source(source)

    assert formatted.endswith("        pass\n    ####\n####\n")
####


def test_one_line_suites_and_semicolon_lists_are_supported() -> None:
    source = (
        "def outer():\n"
        "    if ready: first(); second()\n"
        "    for item in items: consume(item); record(item)\n"
        "    while ready: break\n"
    )

    formatted = scope_markers.format_source(source)

    assert formatted.count("####") == 4
    assert scope_markers.format_source(formatted) == formatted
####


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("def one(): return 1\n", "def one(): return 1\n####\n"),
        ("class One: pass\n", "class One: pass\n####\n"),
        ("if ready: pass\n", "if ready: pass\n####\n"),
        ("for item in items: consume(item)\n", "for item in items: consume(item)\n####\n"),
        ("while ready: break\n", "while ready: break\n####\n"),
        ("with resource: close(resource)\n", "with resource: close(resource)\n####\n"),
        (
                "try: pass\nexcept Exception: recover()\n",
                "try: pass\nexcept Exception: recover()\n####\n",
        ),
        (
                "async def worker(): return 1\n",
                "async def worker(): return 1\n####\n",
        ),
    ],
)
def test_each_one_line_compound_statement_gets_a_boundary(
        source: str, expected: str
) -> None:
    assert scope_markers.format_source(source) == expected
####


def test_semicolon_suite_boundary_follows_the_complete_physical_line() -> None:
    source = "if ready: first(); second(); third()  # trailing\nvalue = 1\n"

    assert scope_markers.format_source(source) == (
        "if ready: first(); second(); third()  # trailing\n"
        "####\n"
        "value = 1\n"
    )
####


def test_one_line_clauses_share_one_boundary() -> None:
    source = (
        "if ready: first()\n"
        "elif retry: second()\n"
        "else: third()\n"
        "after()\n"
    )

    assert scope_markers.format_source(source) == (
        "if ready: first()\n"
        "elif retry: second()\n"
        "else: third()\n"
        "####\n"
        "after()\n"
    )
####


def test_one_line_nested_suite_boundaries_are_depth_ordered() -> None:
    source = "def outer():\n    if ready: first(); second()\n    after()\n"

    assert scope_markers.format_source(source) == (
        "def outer():\n"
        "    if ready: first(); second()\n"
        "    ####\n"
        "    after()\n"
        "####\n"
    )
####


def test_async_one_line_suites_are_marked_inside_the_function() -> None:
    source = (
        "async def worker(items, resource):\n"
        "    async for item in items: consume(item)\n"
        "    async with resource: consume(resource)\n"
    )

    assert scope_markers.format_source(source) == (
        "async def worker(items, resource):\n"
        "    async for item in items: consume(item)\n"
        "    ####\n"
        "    async with resource: consume(resource)\n"
        "    ####\n"
        "####\n"
    )
####


def test_one_line_suite_keeps_a_following_indented_comment_inside_the_scope() -> None:
    source = "def one(): return 1\n    # attached comment\nnext()\n"

    assert scope_markers.format_source(source) == (
        "def one(): return 1\n"
        "    # attached comment\n"
        "####\n"
        "next()\n"
    )
####


def test_extra_blank_lines_do_not_push_markers_to_the_end() -> None:
    source = "class Example:\n    def method(self):\n        pass\n\n\n    value = 1\n\n\n"

    assert scope_markers.format_source(source) == (
        "class Example:\n"
        "    def method(self):\n"
        "        pass\n"
        "    ####\n"
        "\n"
        "\n"
        "    value = 1\n"
        "####\n"
        "\n"
        "\n"
    )
####


def test_ci_command_list_is_explicit_and_uses_the_requested_python() -> None:
    assert ci.ci_commands("python311") == (
        ("python311", "-m", "pytest", "-q"),
        ("python311", "scripts/check_diff.py"),
        ("python311", "-m", "ruff", "check", "src", "scripts", "tests"),
        ("python311", "-m", "flake8", "src", "scripts", "tests"),
        ("python311", "scripts/check_black.py"),
        ("python311", "scripts/check_pyright.py"),
        ("python311", "scripts/check_build.py"),
        ("python311", "-m", "scope_markers", "src", "scripts", "tests"),
        ("python311", "scripts/check_rumdl.py"),
    )
####


def test_check_diff_main_calls_the_bare_cr_check_without_git_argument(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep the standalone bare-CR check's signature aligned with main."""
    called = False

    def find_git(_command: str) -> str:
        return "git"
    ####

    def no_failure(*_args: object, **_kwargs: object) -> None:
        return None
    ####

    def check_bare_cr() -> None:
        nonlocal called
        called = True
    ####


    monkeypatch.setattr(check_diff.shutil, "which", find_git)
    monkeypatch.setattr(check_diff, "_run_diff_case", no_failure)
    monkeypatch.setattr(check_diff, "_check_subdirectory_path", no_failure)
    monkeypatch.setattr(check_diff, "_check_multiple_file_output", no_failure)
    monkeypatch.setattr(check_diff, "_check_autocrlf_modes", no_failure)
    monkeypatch.setattr(check_diff, "_check_bare_cr", check_bare_cr)
    monkeypatch.setattr(check_diff, "_check_newline_filename", no_failure)

    assert check_diff.main() == 0
    assert called
####


def test_ci_fix_mode_adds_safe_formatter_fix_flags() -> None:
    assert ci.ci_commands("python311", fix=True) == (
        ("python311", "-m", "pytest", "-q"),
        ("python311", "scripts/check_diff.py"),
        (
            "python311",
            "-m",
            "ruff",
            "check",
            "--fix",
            "src",
            "scripts",
            "tests",
        ),
        ("python311", "-m", "flake8", "src", "scripts", "tests"),
        ("python311", "scripts/check_black.py"),
        ("python311", "scripts/check_pyright.py"),
        ("python311", "scripts/check_build.py"),
        (
            "python311",
            "-m",
            "scope_markers",
            "--fix",
            "src",
            "scripts",
            "tests",
        ),
        ("python311", "scripts/check_rumdl.py", "--fix"),
    )
####


def test_ci_main_runs_all_commands_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    commands = (("first",), ("second",), ("third",))
    called: list[tuple[str, ...]] = []

    def fake_ci_commands() -> tuple[tuple[str, ...], ...]:
        return commands
    ####


    def record_command(command: tuple[str, ...]) -> int:
        called.append(command)
        return 0
    ####


    monkeypatch.setattr(ci, "ci_commands", fake_ci_commands)
    monkeypatch.setattr(ci, "run_command", record_command)

    assert ci.main() == 0
    assert called == list(commands)
####


def test_ci_main_forwards_fix_option(monkeypatch: pytest.MonkeyPatch) -> None:
    received: list[bool] = []

    def fake_ci_commands(*, fix: bool = False) -> tuple[tuple[str, ...], ...]:
        received.append(fix)
        return ()
    ####


    def successful_command(_command: tuple[str, ...]) -> int:
        return 0
    ####


    monkeypatch.setattr(
        ci,
        "ci_commands",
        fake_ci_commands,
    )
    monkeypatch.setattr(ci, "run_command", successful_command)

    assert ci.main(["--fix"]) == 0
    assert received == [True]
####


def test_ci_help_explains_validation_modes(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exception:
        ci.main(["--help"])
    ####

    output = capsys.readouterr().out
    assert exception.value.code == 0
    assert "same order as CI" in output
    assert "Ruff, scope-markers, and rumdl" in output
    assert "python -m scripts.ci --fix" in output
####


def test_rumdl_help_explains_check_and_fix_modes(
        capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exception:
        check_rumdl.main(["--help"])
    ####

    output = capsys.readouterr().out
    assert exception.value.code == 0
    assert "README.md and CHANGELOG.md" in output
    assert "--fix" in output
    assert "read-only" in output
####


def test_ci_run_command_reports_startup_errors(
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
) -> None:
    def fail_to_start(
            *_args: object, **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("command not found")
    ####


    monkeypatch.setattr(ci.subprocess, "run", fail_to_start)

    assert ci.run_command(("missing-command",)) == 1
    assert "CI command could not start: missing-command" in capsys.readouterr().err
####


def test_ci_main_stops_and_returns_the_first_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    commands = (("first",), ("second",), ("third",))
    called: list[tuple[str, ...]] = []

    def run(command: tuple[str, ...]) -> int:
        called.append(command)
        return 7 if command == commands[1] else 0
    ####


    monkeypatch.setattr(ci, "ci_commands", lambda: commands)
    monkeypatch.setattr(ci, "run_command", run)

    assert ci.main() == 7
    assert called == [commands[0], commands[1]]
####


def test_flake8_configuration_allows_marker_and_black_compatible_syntax(
        tmp_path: Path,
) -> None:
    source = (
        "def first(values: list[int]) -> list[int]:\n"
        "    return values[1 : 2]\n"
        "####\n"
        "def second() -> None:\n"
        "    pass\n"
    )
    path = tmp_path / "marked.py"
    path.write_text(source, encoding="utf-8")
    command = [sys.executable, "-m", "flake8", str(path)]
    project_root = Path(__file__).resolve().parents[1]

    configured = subprocess.run(
        command,
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )
    isolated = subprocess.run(
        [*command[:3], "--isolated", *command[3:]],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert configured.returncode == 0, configured.stdout + configured.stderr
    assert isolated.returncode != 0
    assert "E203" in isolated.stdout or "E203" in isolated.stderr
    assert "E302" in isolated.stdout or "E302" in isolated.stderr
####


def test_black_compatibility_check_passes() -> None:
    assert check_black.main() == 0
####


def test_black_source_copy_skips_non_regular_entries(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mkfifo = cast(Callable[[str], None] | None, getattr(os, "mkfifo", None))
    if mkfifo is None:
        pytest.skip("FIFO creation is unavailable")
    ####

    source_root = tmp_path / "source"
    source_root.mkdir()
    fifo = source_root / "pipe.py"
    try:
        mkfifo(os.fspath(fifo))
    except (OSError, NotImplementedError):
        pytest.skip("FIFO creation is not permitted")
    ####

    destination = tmp_path / "destination"
    monkeypatch.setattr(check_black, "PYTHON_ROOTS", (source_root,))
    check_black._copy_unmarked_sources(destination)  # pyright: ignore[reportPrivateUsage]

    assert not (destination / "pipe.py").exists()
####


def test_black_marker_removal_preserves_unicode_line_separators() -> None:
    source = (
        'value = """first\u2028second\n"""\n'
        "def example() -> None:\n"
        "    pass\n"
        "####\n"
    )

    cleaned = check_black._without_standalone_markers(  # pyright: ignore[reportPrivateUsage]
        source
    )

    assert cleaned == source.removesuffix("####\n")
    compile(cleaned, "unicode-separator.py", "exec")
####


def test_nested_scopes_ending_on_the_same_line_are_ordered_by_depth() -> None:
    source = "def outer():\n    def inner(): pass\n"

    assert scope_markers.format_source(source) == (
        "def outer():\n"
        "    def inner(): pass\n"
        "    ####\n"
        "####\n"
    )
####


@pytest.mark.skipif(
    sys.version_info < (3, 12), reason="generic definitions require Python 3.12"
)
def test_decorated_and_generic_definitions_are_supported_by_the_runtime_parser() -> None:
    source = (
        "@decorator\n"
        "class Box[T]:\n"
        "    @decorator\n"
        "    def get[U](self, value: U) -> U:\n"
        "        return value\n"
    )

    formatted = scope_markers.format_source(source)

    assert formatted.count("####") == 2
####


@pytest.mark.skipif(
    sys.version_info < (3, 13), reason="type-parameter defaults require Python 3.13"
)
def test_type_parameter_defaults_are_supported() -> None:
    source = (
        "class Box[T = int]:\n"
        "    def get[U = T](self, value: U) -> U:\n"
        "        return value\n"
    )

    assert scope_markers.format_source(source).count("####") == 2
####


@pytest.mark.skipif(sys.version_info < (3, 14), reason="PEP 758 syntax requires Python 3.14")
def test_unparenthesized_multiple_except_types_are_supported() -> None:
    source = (
        "try:\n"
        "    connect()\n"
        "except TimeoutError, ConnectionRefusedError:\n"
        "    recover()\n"
    )

    assert scope_markers.format_source(source).count("####") == 1
####


@pytest.mark.skipif(sys.version_info < (3, 14), reason="template strings require Python 3.14")
def test_template_string_marker_text_is_preserved() -> None:
    source = (
        'TEXT = t"""\n'
        "####\n"
        '"""\n'
        "def example() -> None:\n"
        "    pass\n"
    )

    formatted = scope_markers.format_source(source)

    assert 'TEXT = t"""\n####\n"""' in formatted
    assert formatted.count("####") == 2
####


def test_stub_functions_are_skipped_by_default_and_optionally_marked() -> None:
    source = (
        "def documented() -> None:\n"
        "    \"\"\"Documentation only.\"\"\"\n"
        "def ellipsis() -> None: ...\n"
    )

    assert "####" not in scope_markers.format_source(source)
    assert scope_markers.format_source(source, mark_stubs=True).count("####") == 2
####


def test_pass_and_not_implemented_stubs_are_marked() -> None:
    source = (
        "def pass_stub() -> None:\n"
        "    pass\n"
        "def raising_stub() -> None:\n"
        "    raise NotImplementedError\n"
    )

    assert scope_markers.format_source(source).count("####") == 2
####


def test_existing_misplaced_and_duplicate_markers_are_canonicalized() -> None:
    source = (
        "####\n"
        "def example() -> None:\n"
        "    pass\n"
        "    ####\n"
        "####\n"
        "\n"
    )

    assert scope_markers.format_source(source) == (
        "def example() -> None:\n"
        "    pass\n"
        "####\n"
        "\n"
    )
####


def test_marker_like_comments_are_not_owned_by_the_formatter() -> None:
    source = (
        "##### heading\n"
        "#### explanation\n"
        "value = 1  # ####\n"
        "def example() -> None:\n"
        "    pass\n"
    )

    formatted = scope_markers.format_source(source)

    assert "##### heading\n" in formatted
    assert "#### explanation\n" in formatted
    assert "value = 1  # ####\n" in formatted
    assert formatted.count("\n####\n") == 1
####


def test_file_scope_marker_opt_out_preserves_source() -> None:
    source = "# scope-markers: off\ndef example():\n    pass\n"

    assert scope_markers.format_source(source, indent_width=2) == source
    assert scope_markers.format_source(source) == source
    assert scope_markers.explain_source(source) == ()
####


def test_file_scope_marker_opt_out_preserves_unterminated_source() -> None:
    source = "# scope-markers: off\nvalue = (\n"

    assert scope_markers.format_source(source) == source
    assert scope_markers.explain_source(source) == ()
####


def test_ignore_next_skips_one_boundary_but_not_nested_scopes() -> None:
    source = (
        "# scope-markers: ignore-next\n"
        "def outer():\n"
        "    def inner():\n"
        "        pass\n"
        "    pass\n"
    )
    expected = (
        "# scope-markers: ignore-next\n"
        "def outer():\n"
        "    def inner():\n"
        "        pass\n"
        "    ####\n"
        "    pass\n"
    )

    assert scope_markers.format_source(source) == expected
    assert scope_markers.format_source(expected) == expected
####


@pytest.mark.parametrize("marker", ("##", "###", "#####"))
@pytest.mark.parametrize("newline", ("\n", "\r\n", "\r"))
def test_local_hash_marker_style_is_detected_and_preserved(
        marker: str, newline: str
) -> None:
    source = f"def example() -> None:\n    pass\n{marker}\n".replace(
        "\n", newline
    )

    assert scope_markers.format_source(source) == source
####


@pytest.mark.parametrize("marker", ("###", "#####"))
def test_strip_markers_removes_local_hash_marker_style(marker: str) -> None:
    source = f"def example() -> None:\n    pass\n{marker}\nvalue = 1\n"

    assert scope_markers.strip_markers(source) == (
        "def example() -> None:\n    pass\nvalue = 1\n"
    )
####


def test_hash_comment_with_text_is_not_a_marker_style() -> None:
    source = "def example() -> None:\n    pass\n### section\n"

    formatted = scope_markers.format_source(source)

    assert formatted.endswith("####\n### section\n")
####


def test_tabbed_scope_uses_local_indentation_with_detected_marker_style() -> None:
    source = "if outer:\n\tdef example() -> None:\n\t\tpass\n\t##\n##\n"

    assert scope_markers.format_source(source) == (
        "if outer:\n"
        "\tdef example() -> None:\n"
        "\t\tpass\n"
        "\t##\n"
        "##\n"
    )
####


def test_conflicting_marker_styles_are_reported() -> None:
    source = "def first() -> None:\n    pass\n##\ndef second() -> None:\n    pass\n####\n"

    with pytest.raises(
            scope_markers.ScopeMarkersError,
            match="conflicting standalone marker styles: ##, ####; keep one marker style",
    ):
        scope_markers.format_source(source)
    ####
####


def test_marker_text_inside_multiline_string_is_preserved() -> None:
    source = (
        "TEXT = \"\"\"\n"
        "####\n"
        "\"\"\"\n"
        "def example() -> None:\n"
        "    pass\n"
    )

    formatted = scope_markers.format_source(source)

    assert 'TEXT = """\n####\n"""' in formatted
    assert formatted.count("####") == 2
####


def test_unicode_line_separator_inside_string_does_not_corrupt_token_rows() -> None:
    source = (
        "TEXT = 'left\u2028right'\n"
        "def example() -> None:\n"
        "    pass\n"
    )

    formatted = scope_markers.format_source(source)

    assert "left\u2028right" in formatted
    assert formatted.endswith("####\n")
####


def test_trailing_indented_comment_stays_inside_scope() -> None:
    source = (
        "def example() -> None:\n"
        "    pass\n"
        "    # Still visually belongs to example.\n"
        "\n"
    )

    assert scope_markers.format_source(source) == (
        "def example() -> None:\n"
        "    pass\n"
        "    # Still visually belongs to example.\n"
        "####\n"
        "\n"
    )
####


def test_tab_indentation_and_visually_equal_space_comment_are_distinguished() -> None:
    source = (
        "if outer:\n"
        "\tdef example() -> None:\n"
        "\t\tpass\n"
        "        # Same visual indentation as the tabbed def, not inside it.\n"
    )

    assert scope_markers.format_source(source) == (
        "if outer:\n"
        "\tdef example() -> None:\n"
        "\t\tpass\n"
        "\t####\n"
        "        # Same visual indentation as the tabbed def, not inside it.\n"
        "####\n"
    )
####


def test_mixed_valid_space_widths_keep_each_scope_indent() -> None:
    source = (
        "class Example:\n"
        "  def first(self):\n"
        "      if ready:\n"
        "          pass\n"
        "      ##\n"
        "  def second(self):\n"
        "      pass\n"
        "##\n"
    )

    assert scope_markers.format_source(source) == (
        "class Example:\n"
        "  def first(self):\n"
        "      if ready:\n"
        "          pass\n"
        "      ##\n"
        "  ##\n"
        "  def second(self):\n"
        "      pass\n"
        "  ##\n"
        "##\n"
    )
####


def test_tabbed_nesting_uses_local_indentation_and_detected_marker_style() -> None:
    source = (
        "class Example:\n"
        "\tdef first(self):\n"
        "\t\tif ready:\n"
        "\t\t\tpass\n"
        "\t\t##\n"
        "\t##\n"
        "##\n"
    )

    assert scope_markers.format_source(source) == (
        "class Example:\n"
        "\tdef first(self):\n"
        "\t\tif ready:\n"
        "\t\t\tpass\n"
        "\t\t##\n"
        "\t##\n"
        "##\n"
    )
####


def test_top_level_function_marker_returns_to_column_zero_after_tabbed_body() -> None:
    source = "def example():\n\tpass\n####\n"

    assert scope_markers.format_source(source) == "def example():\n\tpass\n####\n"
####


def test_inconsistent_tab_and_space_indentation_is_reported(tmp_path: Path) -> None:
    path = tmp_path / "inconsistent.py"
    path.write_bytes(b"if outer:\n\tpass\n    pass\n")

    changed, error = scope_markers.process_file(path, fix=False)

    assert changed is False
    assert error is not None
    assert "indent" in error
####


def test_form_feed_indentation_is_preserved() -> None:
    source = "if ready:\n\f    pass\n"

    assert scope_markers.format_source(source) == "if ready:\n\f    pass\n####\n"
####


def test_missing_final_newline_is_repaired_before_marker() -> None:
    source = "def example() -> None:\n    pass"

    assert scope_markers.format_source(source) == "def example() -> None:\n    pass\n####\n"
####


def test_unterminated_final_scope_uses_nearest_newline() -> None:
    source = "def first():\r\n    pass\r\ndef final():\n    pass"

    assert scope_markers.format_source(source) == (
        "def first():\r\n"
        "    pass\r\n"
        "####\r\n"
        "def final():\n"
        "    pass\n"
        "####\n"
    )
####


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_newline_convention_is_preserved(newline: str) -> None:
    source = newline.join(("def example() -> None:", "    pass", ""))

    assert scope_markers.format_source(source) == newline.join(
        ("def example() -> None:", "    pass", "####", "")
    )
####


def test_mixed_newlines_use_the_local_preceding_line_ending() -> None:
    source = "def first():\r\n    pass\r\n\r\ndef second():\n    pass\n"

    assert scope_markers.format_source(source) == (
        "def first():\r\n"
        "    pass\r\n"
        "####\r\n"
        "\r\n"
        "def second():\n"
        "    pass\n"
        "####\n"
    )
####


def test_large_source_with_many_compound_statements_is_stable() -> None:
    source = "".join(
        f"def function_{index}():\n    pass\n" for index in range(1_000)
    )

    formatted = scope_markers.format_source(source)

    assert formatted.count("####") == 1_000
    assert scope_markers.format_source(formatted) == formatted
####


def test_extremely_long_physical_line_is_preserved() -> None:
    value = "x" * 100_000
    source = f"value = '{value}'\ndef example():\n    pass\n"

    formatted = scope_markers.format_source(source)

    assert f"value = '{value}'\n" in formatted
    assert formatted.endswith("    pass\n####\n")
####


def test_non_utf8_source_encoding_and_cookie_are_preserved(tmp_path: Path) -> None:
    path = tmp_path / "latin1.py"
    path.write_bytes(
        b"# -*- coding: latin-1 -*-\n"
        b"LABEL = 'caf\xe9'\n"
        b"def example() -> None:\n"
        b"    pass\n"
    )

    assert scope_markers.process_file(path, fix=True) == (True, None)
    assert b"caf\xe9" in path.read_bytes()
    assert path.read_bytes().startswith(b"# -*- coding: latin-1 -*-")
####


def test_cp1252_source_encoding_is_supported(tmp_path: Path) -> None:
    path = tmp_path / "cp1252.py"
    path.write_bytes(
        b"# coding: cp1252\n"
        b"LABEL = '\x80'\n"
        b"def example() -> None:\n"
        b"    pass\n"
    )

    assert scope_markers.process_file(path, fix=True) == (True, None)
    assert b"LABEL = '\x80'" in path.read_bytes()
    assert path.read_bytes().endswith(b"    pass\n####\n")
####


def test_utf8_bom_is_preserved(tmp_path: Path) -> None:
    path = tmp_path / "bom.py"
    path.write_bytes(b"\xef\xbb\xbfdef example():\n    pass\n")

    assert scope_markers.process_file(path, fix=True) == (True, None)
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")
####


@pytest.mark.skipif(os.name == "nt", reason="Windows does not expose Unix executable bits")
def test_atomic_fix_preserves_executable_bits(tmp_path: Path) -> None:
    path = tmp_path / "tool.py"
    path.write_text("def main():\n    pass\n", encoding="utf-8")
    path.chmod(0o751)

    assert scope_markers.process_file(path, fix=True) == (True, None)
    assert stat.S_IMODE(path.stat().st_mode) == 0o751
####


def test_cli_fix_updates_an_explicit_symlink_without_replacing_it(tmp_path: Path) -> None:
    if not hasattr(os, "symlink"):
        pytest.skip("symlinks are unavailable")
    ####
    target = tmp_path / "target.py"
    link = tmp_path / "link.py"
    target.write_text("def example():\n    pass\n", encoding="utf-8")
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation is not permitted")
    ####

    files, errors = scope_markers.discover_python_files([link])

    assert files == [link]
    assert errors == []
    assert cli.main(["--fix", "--quiet", str(link)]) == 0
    assert link.is_symlink()
    assert target.read_text(encoding="utf-8").endswith("####\n")
####


def test_recursive_discovery_skips_symlinked_files_and_generated_directories(
        tmp_path: Path,
) -> None:
    source = tmp_path / "source.py"
    source.write_text("pass\n", encoding="utf-8")
    generated = tmp_path / ".venv"
    generated.mkdir()
    (generated / "ignored.py").write_text("pass\n", encoding="utf-8")
    link = tmp_path / "linked.py"
    with suppress(OSError):
        link.symlink_to(source)
    ####

    files, errors = scope_markers.discover_python_files([tmp_path])

    assert files == [source]
    assert errors == []
####


def test_discovery_reports_missing_and_non_python_explicit_paths(tmp_path: Path) -> None:
    text = tmp_path / "notes.txt"
    text.write_text("notes", encoding="utf-8")

    files, errors = scope_markers.discover_python_files([tmp_path / "missing", text])

    assert files == []
    assert len(errors) == 2
    assert "does not exist" in errors[0]
    assert "expected a supported source file" in errors[1]
####


def test_legacy_python_files_api_deduplicates_and_sorts(tmp_path: Path) -> None:
    first = tmp_path / "a.py"
    second = tmp_path / "b.py"
    first.write_text("pass\n", encoding="utf-8")
    second.write_text("pass\n", encoding="utf-8")

    assert scope_markers.python_files([second, first, second]) == [first, second]
####


def test_discovery_deduplicates_relative_and_absolute_root_spellings(tmp_path: Path) -> None:
    source = tmp_path / "module.py"
    source.write_text("pass\n", encoding="utf-8")
    relative_root = Path(os.path.relpath(tmp_path, Path.cwd()))

    files, errors = scope_markers.discover_python_files([relative_root, tmp_path])

    assert files == [relative_root / "module.py"]
    assert errors == []
####


def test_cli_does_not_emit_duplicate_diff_for_equivalent_roots(
        tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "module.py"
    source.write_text("def example():\n    pass\n", encoding="utf-8")
    relative_root = Path(os.path.relpath(tmp_path, Path.cwd()))

    assert cli.main(["--diff", str(relative_root), str(tmp_path)]) == 1
    output = capsys.readouterr().out

    assert output.count("\n@@ ") == 1
####


def test_discovery_prunes_generated_directories_recursively(tmp_path: Path) -> None:
    source = tmp_path / "src" / "module.py"
    source.parent.mkdir()
    source.write_text("pass\n", encoding="utf-8")
    ignored = tmp_path / "build" / "module.py"
    ignored.parent.mkdir()
    ignored.write_text("pass\n", encoding="utf-8")

    files, errors = scope_markers.discover_python_files([tmp_path])

    assert files == [source]
    assert errors == []
####


def test_discovery_skips_an_explicit_symlinked_directory_root(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    (target / "module.py").write_text("pass\n", encoding="utf-8")
    link = tmp_path / "linked-root"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is not permitted")
    ####

    files, errors = scope_markers.discover_python_files([link])

    assert files == []
    assert errors == []
####


def test_discovery_skips_a_generated_directory_when_it_is_the_root(tmp_path: Path) -> None:
    generated = tmp_path / "build"
    generated.mkdir()
    source = generated / "module.py"
    source.write_text("pass\n", encoding="utf-8")

    files, errors = scope_markers.discover_python_files([generated])

    assert files == []
    assert errors == []
####


def test_discovery_treats_generated_directory_names_case_insensitively(
        tmp_path: Path,
) -> None:
    generated = tmp_path / "BUILD"
    generated.mkdir()
    (generated / "module.py").write_text("pass\n", encoding="utf-8")

    files, errors = scope_markers.discover_python_files([tmp_path])

    assert files == []
    assert errors == []
####


def test_discovery_skips_a_root_inside_a_generated_directory(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    generated = tmp_path / ".venv"
    nested = generated / "package"
    nested.mkdir(parents=True)
    (nested / "module.py").write_text("pass\n", encoding="utf-8")
    monkeypatch.chdir(nested)

    files, errors = scope_markers.discover_python_files([Path(".")])

    assert files == []
    assert errors == []
####


def test_discovery_can_disable_default_directory_exclusions(tmp_path: Path) -> None:
    generated = tmp_path / ".venv"
    generated.mkdir()
    source = generated / "module.py"
    source.write_text("pass\n", encoding="utf-8")

    files, errors = scope_markers.discover_python_files(
        [generated], use_default_excludes=False
    )

    assert files == [source]
    assert errors == []
####


def test_discovery_skips_egg_info_directories_by_default(tmp_path: Path) -> None:
    metadata = tmp_path / "scope_markers.egg-info"
    metadata.mkdir()
    source = metadata / "generated.py"
    source.write_text("pass\n", encoding="utf-8")

    files, errors = scope_markers.discover_python_files([tmp_path])

    assert files == []
    assert errors == []
####


def test_discovery_supports_multiple_roots_and_exclude_patterns(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    ignored = second / "generated"
    first.mkdir()
    ignored.mkdir(parents=True)
    first_source = first / "first.py"
    second_source = second / "second.py"
    ignored_source = ignored / "ignored.py"
    for path in (first_source, second_source, ignored_source):
        path.write_text("pass\n", encoding="utf-8")
    ####

    files, errors = scope_markers.discover_python_files(
        [first, second], exclude_patterns=("generated",)
    )

    assert files == [first_source, second_source]
    assert errors == []
####


def test_discovery_matches_absolute_include_and_exclude_patterns(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vendor = tmp_path / "vendor"
    other = tmp_path / "other"
    vendor.mkdir()
    other.mkdir()
    (vendor / "ignored.py").write_text("pass\n", encoding="utf-8")
    (tmp_path / "kept.py").write_text("pass\n", encoding="utf-8")
    (other / "included.bzl").write_text("def rule():\n    pass\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    discovered, errors = api.discover_python_files(
        [Path(".")],
        include_patterns=((other / "*.bzl").absolute().as_posix(),),
        exclude_patterns=((vendor / "*.py").absolute().as_posix(),),
    )

    assert sorted(path.as_posix() for path in discovered) == [
        "kept.py",
        "other/included.bzl",
    ]
    assert errors == []
####


def test_recursive_discovery_skips_non_regular_supported_entries(tmp_path: Path) -> None:
    mkfifo = cast(Callable[[str], None] | None, getattr(os, "mkfifo", None))
    if mkfifo is None:
        pytest.skip("FIFO creation is unavailable")
    ####

    fifo = tmp_path / "pipe.py"
    try:
        mkfifo(os.fspath(fifo))
    except (OSError, NotImplementedError):
        pytest.skip("FIFO creation is not permitted")
    ####

    files, errors = api.discover_python_files([tmp_path])

    assert files == []
    assert errors == []
####


def test_discovery_include_patterns_allow_python_compatible_extensions(tmp_path: Path) -> None:
    starlark = tmp_path / "BUILD.bzl"
    starlark.write_text("def rule():\n    pass\n", encoding="utf-8")

    files, errors = scope_markers.discover_python_files([tmp_path])
    assert files == []
    assert errors == []

    files, errors = scope_markers.discover_python_files(
        [tmp_path], include_patterns=("*.bzl",)
    )

    assert files == [starlark]
    assert errors == []
    assert cli.main(["--include", "*.bzl", "--fix", "--quiet", str(tmp_path)]) == 0
    assert starlark.read_text(encoding="utf-8").endswith("####\n")
####


def test_stub_discovery_and_formatting_require_mark_stubs_opt_in(tmp_path: Path) -> None:
    stub = tmp_path / "interfaces.pyi"
    stub.write_text("def connect() -> None: ...\n", encoding="utf-8")

    files, errors = api.discover_python_files([tmp_path])
    assert files == []
    assert errors == []

    files, errors = api.discover_python_files([stub])
    assert files == []
    assert errors == [f"{stub}: expected a supported source file or directory"]

    files, errors = api.discover_python_files([tmp_path], include_stubs=True)
    assert files == [stub]
    assert errors == []
    assert api.python_files([stub], include_stubs=True) == [stub]

    assert cli.main(["--fix", "--quiet", str(tmp_path)]) == 0
    assert stub.read_text(encoding="utf-8") == "def connect() -> None: ...\n"

    assert cli.main(["--mark-stubs", "--fix", "--quiet", str(tmp_path)]) == 0
    assert stub.read_text(encoding="utf-8") == "def connect() -> None: ...\n####\n"
####


def test_cli_mark_stubs_option_is_forwarded(tmp_path: Path) -> None:
    path = tmp_path / "stub.py"
    path.write_text("def example() -> None: ...\n", encoding="utf-8")

    assert cli.main(["--mark-stubs", str(path)]) == 1
    assert cli.main(["--mark-stubs", "--fix", "--quiet", str(path)]) == 0
    assert path.read_text(encoding="utf-8").endswith("####\n")
####


def test_cli_indent_width_reindents_and_marks_in_one_fix(tmp_path: Path) -> None:
    path = tmp_path / "example.py"
    path.write_text("def example():\n    pass\n", encoding="utf-8")

    assert cli.main(["--indent-width", "2", "--fix", "--quiet", str(path)]) == 0
    assert path.read_text(encoding="utf-8") == "def example():\n  pass\n####\n"
####


def test_cli_accepts_multiple_roots_and_exclude_patterns(tmp_path: Path) -> None:
    first = tmp_path / "first.py"
    second_root = tmp_path / "second"
    second_root.mkdir()
    second = second_root / "second.py"
    ignored_root = second_root / "generated"
    ignored_root.mkdir()
    ignored = ignored_root / "ignored.py"
    for path in (first, second, ignored):
        path.write_text("def example():\n    pass\n", encoding="utf-8")
    ####

    assert cli.main(["--exclude", "generated", str(first), str(second_root)]) == 1
    assert cli.main(
        ["--exclude", "generated", "--fix", "--quiet", str(first), str(second_root)]
    ) == 0
    assert first.read_text(encoding="utf-8").endswith("####\n")
    assert second.read_text(encoding="utf-8").endswith("####\n")
    assert not ignored.read_text(encoding="utf-8").endswith("####\n")
####


def test_cli_default_excludes_can_be_disabled(tmp_path: Path) -> None:
    generated = tmp_path / ".uv-cache"
    generated.mkdir()
    source = generated / "module.py"
    source.write_text("def example():\n    pass\n", encoding="utf-8")

    assert cli.main(["--fix", "--quiet", str(tmp_path)]) == 0
    assert not source.read_text(encoding="utf-8").endswith("####\n")

    assert cli.main(
        ["--no-default-excludes", "--fix", "--quiet", str(tmp_path)]
    ) == 0
    assert source.read_text(encoding="utf-8").endswith("####\n")
####


def test_cli_supports_repeated_exclude_patterns(tmp_path: Path) -> None:
    first = tmp_path / "first.py"
    second = tmp_path / "second.generated.py"
    first.write_text("def example():\n    pass\n", encoding="utf-8")
    second.write_text("def example():\n    pass\n", encoding="utf-8")

    assert cli.main(
        ["--exclude", "*.generated.py", "--exclude", "unused", str(tmp_path)]
    ) == 1
    assert not first.read_text(encoding="utf-8").endswith("####\n")
    assert not second.read_text(encoding="utf-8").endswith("####\n")
####


def test_token_error_reports_line_and_column(tmp_path: Path) -> None:
    path = tmp_path / "unfinished.py"
    path.write_text('value = "unterminated\n', encoding="utf-8")

    changed, error = scope_markers.process_file(path, fix=False)

    assert changed is False
    assert error is not None
    assert f"{path}:" in error
####


def test_process_file_reports_missing_input_file(tmp_path: Path) -> None:
    path = tmp_path / "missing.py"

    changed, error = scope_markers.process_file(path, fix=False)

    assert changed is False
    assert error is not None
    assert str(path) in error
####


def test_version_is_loaded_from_installed_metadata() -> None:
    assert scope_markers.__version__ == installed_version("scope-markers")
####


def test_package_init_does_not_reexport_implementation_api() -> None:
    assert not hasattr(package, "format_source")
    assert not hasattr(package, "process_file")
    assert not hasattr(package, "main")
####


def test_programmatic_api_exposes_stable_formatter_functions() -> None:
    assert api.format_source("def example():\n    pass\n").endswith("####\n")
    assert api.process_file is scope_markers.process_file
    assert api.strip_markers is scope_markers.strip_markers
    assert api.strip_file is scope_markers.strip_file
    assert api.discover_python_files is scope_markers.discover_python_files
    assert issubclass(api.ScopeMarkersError, ValueError)
####


@pytest.mark.parametrize("newline", ("\n", "\r\n", "\r"))
def test_strip_markers_removes_only_standalone_recognized_comments(newline: str) -> None:
    source = (
        "if enabled:\n"
        "    value = '####'\n"
        "####\n"
        "##\n"
        "#### trailing explanation\n"
        "    # ####\n"
        "not valid Python\n"
    ).replace("\n", newline)

    assert api.strip_markers(source) == (
        "if enabled:\n"
        "    value = '####'\n"
        "#### trailing explanation\n"
        "    # ####\n"
        "not valid Python\n"
    ).replace("\n", newline)
####


def test_strip_markers_preserves_markers_inside_multiline_strings_and_mixed_endings() -> None:
    source = (
        'description = """A marker-looking line follows:\r\n'
        "####\r\n"
        '"""\r\n'
        "####\r\n"
        "value = 1\n"
        "##\n"
    )

    assert api.strip_markers(source) == (
        'description = """A marker-looking line follows:\r\n'
        "####\r\n"
        '"""\r\n'
        "value = 1\n"
    )
####


def test_strip_file_preserves_source_encoding_and_reports_missing_files(tmp_path: Path) -> None:
    path = tmp_path / "cp1252.py"
    source = b"# coding: cp1252\r\nlabel = '\xe9'\r\n####\r\n"
    path.write_bytes(source)

    assert api.strip_file(path, fix=False) == (True, None)
    assert api.strip_file(path, fix=True) == (True, None)
    assert path.read_bytes() == b"# coding: cp1252\r\nlabel = '\xe9'\r\n"

    changed, error = api.strip_file(tmp_path / "missing.py", fix=True)
    assert changed is False
    assert error is not None
    assert "missing.py" in error
####


def test_strip_file_returns_diagnostic_for_invalid_encoding_declaration(
        tmp_path: Path,
) -> None:
    path = tmp_path / "invalid-encoding.py"
    path.write_bytes(b"# coding: not-a-real-encoding\n####\n")

    changed, error = api.strip_file(path, fix=True)

    assert changed is False
    assert error is not None
    assert "invalid-encoding.py" in error
    assert "unknown encoding" in error
    assert path.read_bytes().endswith(b"####\n")
####


def test_strip_file_recovers_from_invalid_unindent_before_marker(
        tmp_path: Path,
) -> None:
    path = tmp_path / "invalid-unindent.py"
    path.write_text("if ready:\n    pass\n  ####\n", encoding="utf-8")

    assert api.strip_file(path, fix=True) == (True, None)
    assert path.read_text(encoding="utf-8") == "if ready:\n    pass\n"
####


def test_programmatic_api_surface_is_complete_and_usable(tmp_path: Path) -> None:
    assert api.__all__ == (
        "BoundaryExplanation",
        "BoundaryKind",
        "FileInspection",
        "MarkerPolicy",
        "PolicyDecision",
        "PolicyError",
        "ScopeBoundary",
        "ScopeMarkersError",
        "__version__",
        "describe_policy",
        "discover_python_files",
        "expand_selectors",
        "explain_file",
        "explain_source",
        "find_config",
        "format_markdown_source",
        "format_source",
        "inspect_file",
        "inspect_markdown_file",
        "inspect_stripped_file",
        "load_policy",
        "process_file",
        "process_markdown_file",
        "python_files",
        "resolve_policy",
        "statements_policy",
        "strip_file",
        "strip_markers",
    )
    assert api.__version__ == installed_version("scope-markers")

    path = tmp_path / "example.py"
    path.write_text("def example():\n    pass\n", encoding="utf-8")
    inspection = api.inspect_file(path)

    assert isinstance(inspection, api.FileInspection)
    assert inspection.path == path
    assert inspection.changed is True
    assert api.format_source(inspection.source) == inspection.formatted
    assert api.process_file(path, fix=False) == (True, None)
    assert api.process_file(path, fix=True) == (True, None)
    assert api.process_file(path, fix=False) == (False, None)

    assert api.process_file(path, fix=True) == (False, None)
    assert api.strip_file(path, fix=False) == (True, None)
    assert api.inspect_stripped_file(path).formatted == inspection.source
    assert api.strip_file(path, fix=True) == (True, None)
    assert api.strip_file(path, fix=False) == (False, None)

    starlark = tmp_path / "BUILD.bzl"
    starlark.write_text("def rule():\n    pass\n", encoding="utf-8")
    discovered, errors = api.discover_python_files(
        [tmp_path], include_patterns=("*.bzl",), exclude_patterns=("example.py",)
    )

    assert discovered == [starlark]
    assert errors == []
    assert api.python_files([starlark], include_patterns=("*.bzl",)) == [starlark]

    boundary = api.ScopeBoundary(0, "", 0, 1)
    assert boundary.line_number == 1
####


def test_marker_policy_can_select_existing_boundary_kinds_and_filter_shapes() -> None:
    source = (
        "def outer():\n"
        "    if ready:\n"
        "        work()\n"
        "match value:\n"
        "    case 1:\n"
        "        handle()\n"
        "    case _:\n"
        "        fallback()\n"
    )
    definitions = api.MarkerPolicy(selected=api.expand_selectors(("definitions",)))
    complete_statements = api.MarkerPolicy(
        selected=api.expand_selectors(("complete-statements",))
    )
    cases = api.MarkerPolicy(selected=api.expand_selectors(("clause.match.case",)))
    statements = api.statements_policy()
    all_boundaries = api.MarkerPolicy(selected=api.expand_selectors(("all",)))
    nested = api.MarkerPolicy(
        selected=api.expand_selectors(("complete-statements",)), min_depth=1
    )

    assert api.format_source(source) == api.format_source(source, policy=statements)
    assert api.format_source(source, policy=definitions).count("####") == 1
    assert api.format_source(source, policy=complete_statements).count("####") == 3
    assert api.format_source(source, policy=statements).count("####") == 4
    assert api.format_source(source, policy=cases).count("####") == 2
    assert api.format_source(source, policy=all_boundaries).count("####") == 5
    assert api.format_source(source, policy=nested).count("####") == 1
####


def test_marker_policy_filters_inline_and_short_suites() -> None:
    source = "if ready: work()\nif (\n    later\n): work()\nif tomorrow:\n    work()\n"
    policy = api.MarkerPolicy(
        selected=api.expand_selectors(("statement.if",)),
        skip_inline_suites=True,
        min_body_lines=2,
    )

    assert api.format_source(source, policy=policy) == source
####


def test_clause_selectors_mark_each_if_branch_without_duplicate_final_marker() -> None:
    source = (
        "if first:\n"
        "    handle_first()\n"
        "elif second:\n"
        "    handle_second()\n"
        "else:\n"
        "    handle_default()\n"
    )
    all_boundaries = api.MarkerPolicy(selected=api.expand_selectors(("all",)))
    final_else = api.MarkerPolicy(selected=api.expand_selectors(("clause.if.else",)))

    assert api.expand_selectors(("clause.if",)) == frozenset(
        {
            api.BoundaryKind.CLAUSE_IF_BODY,
            api.BoundaryKind.CLAUSE_IF_ELIF,
            api.BoundaryKind.CLAUSE_IF_ELSE,
        }
    )
    assert api.format_source(source, policy=all_boundaries) == (
        "if first:\n"
        "    handle_first()\n"
        "####\n"
        "elif second:\n"
        "    handle_second()\n"
        "####\n"
        "else:\n"
        "    handle_default()\n"
        "####\n"
    )
    assert api.format_source(source, policy=final_else).endswith(
        "else:\n    handle_default()\n####\n"
    )
####


@pytest.mark.parametrize("newline", ("\n", "\r\n", "\r"))
def test_loop_and_try_clause_selectors_mark_owned_suites(newline: str) -> None:
    source = (
        "for item in items:\n"
        "    handle(item)\n"
        "else:\n"
        "    finish()\n"
        "while ready:\n"
        "    wait()\n"
        "else:\n"
        "    recover()\n"
        "try:\n"
        "    work()\n"
        "except OSError:\n"
        "    repair()\n"
        "else:\n"
        "    commit()\n"
        "finally:\n"
        "    close()\n"
    )
    policy = api.MarkerPolicy(selected=api.expand_selectors(("loops", "exceptions")))

    formatted = api.format_source(source.replace("\n", newline), policy=policy)

    assert formatted.count("####") == 8
    assert f"    handle(item){newline}####{newline}else:" in formatted
    assert f"    repair(){newline}####{newline}else:" in formatted
    assert f"    close(){newline}####{newline}" in formatted
    assert api.format_source(formatted, policy=policy) == formatted
####


def test_inline_clause_suites_respect_policy_filters() -> None:
    source = "try: work()\nexcept OSError: repair()\nfinally: close()\n"
    policy = api.MarkerPolicy(
        selected=api.expand_selectors(("clause.try",)),
        skip_inline_suites=True,
    )

    assert api.format_source(source, policy=policy) == source
####


@pytest.mark.parametrize("newline", ("\n", "\r\n", "\r"))
def test_except_star_clause_selector_uses_the_handler_header(newline: str) -> None:
    source = (
        "try:\n"
        "    work()\n"
        "# A comment must not hide the following clause header.\n"
        "except* OSError:\n"
        "    repair()\n"
    ).replace("\n", newline)
    policy = api.MarkerPolicy(selected=api.expand_selectors(("clause.try.except",)))

    assert api.format_source(source, policy=policy) == (
        "try:"
        f"{newline}"
        "    work()"
        f"{newline}"
        "# A comment must not hide the following clause header."
        f"{newline}"
        "except* OSError:"
        f"{newline}"
        "    repair()"
        f"{newline}"
        "####"
        f"{newline}"
    )
####


def test_policy_toml_is_strict_and_can_change_cli_output(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "example.py"
    source.write_text("if ready:\n    work()\n", encoding="utf-8")
    config = tmp_path / "scope-markers.toml"
    config.write_text('preset = "definitions"\n', encoding="utf-8")

    policy = api.load_policy(config)
    assert api.format_source(source.read_text(encoding="utf-8"), policy=policy) == (
        "if ready:\n    work()\n"
    )
    assert cli.main(["--config", str(config), "--quiet", str(source)]) == 0
    assert cli.main(["--config", str(config), "--show-settings", str(source)]) == 0
    assert "select = [statement.class, statement.function]" in capsys.readouterr().out

    config.write_text('select = ["statement.iff"]\n', encoding="utf-8")
    with pytest.raises(api.PolicyError, match="unknown selector"):
        api.load_policy(config)
    ####
####


def test_readme_complete_policy_example_is_accepted(tmp_path: Path) -> None:
    readme = (Path(__file__).parents[1] / "README.md").read_text(encoding="utf-8")
    match = re.search(
        r"The complete accepted configuration shape.*?```toml\n(.*?)```",
        readme,
        re.DOTALL,
    )
    assert match is not None

    config = tmp_path / "pyproject.toml"
    config.write_text(match.group(1), encoding="utf-8")

    policy = api.load_policy(config)

    assert api.BoundaryKind.STATEMENT_FUNCTION in policy.selected
    assert api.BoundaryKind.CLAUSE_IF_BODY in policy.selected
####


def test_per_file_policy_overrides_apply_in_declaration_order(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = tmp_path / "scope-markers.toml"
    source = tmp_path / "src" / "module.py"
    test_source = tmp_path / "tests" / "unit" / "module.py"
    source.parent.mkdir()
    test_source.parent.mkdir(parents=True)
    source.write_text("if ready:\n    work()\n", encoding="utf-8")
    test_source.write_text("if ready:\n    work()\n", encoding="utf-8")
    config.write_text(
        "preset = \"definitions\"\n"
        "\n"
        "[[per-file]]\n"
        "patterns = [\"tests/**\"]\n"
        "preset = \"statements\"\n"
        "extend-select = [\"clause.if\"]\n"
        "\n"
        "[[per-file]]\n"
        "patterns = [\"tests/unit/**\"]\n"
        "ignore = [\"clause.if.body\"]\n",
        encoding="utf-8",
    )

    source_policy = api.resolve_policy(config, source)
    test_policy = api.resolve_policy(config, test_source)

    assert source_policy.selected == api.expand_selectors(("definitions",))
    assert api.BoundaryKind.CLAUSE_IF_ELIF in test_policy.selected
    assert api.BoundaryKind.CLAUSE_IF_ELSE in test_policy.selected
    assert api.BoundaryKind.CLAUSE_IF_BODY not in test_policy.selected
    assert cli.main(["--config", str(config), "--quiet", str(source)]) == 0
    assert cli.main(["--config", str(config), "--quiet", str(test_source)]) == 1
    assert cli.main(["--config", str(config), "--show-settings", str(test_source)]) == 0
    assert "clause.if.else" in capsys.readouterr().out
####


def test_symlink_policy_uses_lexical_path_and_config_location(tmp_path: Path) -> None:
    source = tmp_path / "external" / "module.py"
    link = tmp_path / "src" / "link.py"
    config = tmp_path / "scope-markers.toml"
    source.parent.mkdir()
    link.parent.mkdir()
    source.write_text("def example():\n    pass\n", encoding="utf-8")
    config.write_text(
        'preset = "none"\n\n'
        '[[per-file]]\n'
        'patterns = ["src/**"]\n'
        'extend-select = ["statement.function"]\n',
        encoding="utf-8",
    )
    try:
        link.symlink_to(source)
    except OSError:
        pytest.skip("symlink creation is not permitted")
    ####

    assert api.find_config(link) == config
    policy = api.resolve_policy(config, link)
    assert api.BoundaryKind.STATEMENT_FUNCTION in policy.selected
    assert cli.main(["--fix", "--quiet", str(link)]) == 0
    assert source.read_text(encoding="utf-8").endswith("####\n")
####


def test_per_file_policy_overrides_are_strict(tmp_path: Path) -> None:
    config = tmp_path / "scope-markers.toml"
    config.write_text(
        "[[per-file]]\n"
        "patterns = [\"src/**\"]\n"
        "unknown-option = true\n",
        encoding="utf-8",
    )

    with pytest.raises(api.PolicyError, match="per-file override 1"):
        api.load_policy(config)
    ####

    config.write_text("[[per-file]]\npreset = \"none\"\n", encoding="utf-8")
    with pytest.raises(api.PolicyError, match="requires at least one pattern"):
        api.load_policy(config)
    ####

    config.write_text(
        '[[per-file]]\npatterns = [""]\n', encoding="utf-8"
    )
    with pytest.raises(api.PolicyError, match="patterns must not be empty"):
        api.load_policy(config)
    ####
####


def test_explain_source_reports_filter_and_duplicate_decisions() -> None:
    source = "if ready:\n    work()\nelse:\n    recover()\n"
    all_policy = api.MarkerPolicy(selected=api.expand_selectors(("all",)))
    inline_policy = api.MarkerPolicy(
        selected=api.expand_selectors(("statement.if",)),
        skip_inline_suites=True,
    )

    explanations = api.explain_source(source, policy=all_policy)
    inline_explanation = api.explain_source("if ready: work()\n", policy=inline_policy)

    assert any(
        explanation.kind is api.BoundaryKind.STATEMENT_IF
        and explanation.will_mark
        and explanation.reason == "selected"
        for explanation in explanations
    )
    assert any(
        explanation.kind is api.BoundaryKind.CLAUSE_IF_ELSE
        and not explanation.will_mark
        and explanation.reason == "duplicates selected statement.if boundary"
        for explanation in explanations
    )
    assert inline_explanation[0].reason == "inline suite is skipped"
####


def test_match_case_rules_inherit_owning_match_facts(tmp_path: Path) -> None:
    config = tmp_path / "scope-markers.toml"
    config.write_text(
        'select = ["clause.match.case"]\n'
        '\n'
        '[rules."clause.match.case"]\n'
        'require = ["function-level", "nested"]\n',
        encoding="utf-8",
    )
    source = (
        "def outer(value: object) -> None:\n"
        "    match value:\n"
        "        case 1:\n"
        "            pass\n"
    )

    policy = api.load_policy(config)

    assert api.format_source(source, policy=policy).endswith(
        "            pass\n        ####\n"
    )
####


def test_cli_explain_reports_resolved_policy_decisions(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "inline.py"
    source.write_text("if ready: work()\n", encoding="utf-8")

    assert cli.main(
        ["--select", "statement.if", "--skip-inline-suites", "--explain", str(source)]
    ) == 0

    output = capsys.readouterr().out
    assert f"{source}:1: skip statement.if: inline suite is skipped" in output
####


def test_cli_rejects_explain_with_an_incompatible_operation(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "example.py"
    source.write_text("pass\n", encoding="utf-8")

    with pytest.raises(SystemExit) as error:
        cli.main(["--fix", "--explain", str(source)])
    ####

    assert error.value.code == 2
    assert "--explain cannot be used with --fix or --diff" in capsys.readouterr().err
####


def test_policy_rule_predicates_and_nearest_config_apply_per_file(tmp_path: Path) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    source = nested / "example.py"
    source.write_text("if ready:\n    work()\n", encoding="utf-8")
    (tmp_path / "scope-markers.toml").write_text('preset = "definitions"\n', encoding="utf-8")
    (nested / "scope-markers.toml").write_text(
        "select = [\"statement.if\"]\n"
        "[rules.\"statement.if\"]\nrequire = [\"has-else\"]\n",
        encoding="utf-8",
    )

    assert cli.main(["--fix", "--quiet", str(source)]) == 0
    assert source.read_text(encoding="utf-8") == "if ready:\n    work()\n"

    assert api.load_policy(nested / "scope-markers.toml").selected == frozenset(
        {api.BoundaryKind.STATEMENT_IF}
    )
####


def test_cli_policy_options_are_listed_and_rejected_while_stripping(
        capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["--list-selectors"]) == 0
    assert "statement.function" in capsys.readouterr().out

    with pytest.raises(SystemExit) as error:
        cli.main(["--strip", "--preset", "definitions"])
    ####

    assert error.value.code == 2
    assert "marker-policy options cannot be used with --strip" in capsys.readouterr().err
####


@pytest.mark.parametrize("option", ("--select", "--extend-select", "--ignore"))
@pytest.mark.parametrize("selector", ("", ",", "statement.if,", ",statement.if"))
def test_cli_rejects_empty_selector_components(
        option: str, selector: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "example.py"
    source.write_text("def example():\n    pass\n", encoding="utf-8")

    assert cli.main([option, selector, "--quiet", str(source)]) == 2
    assert "selector names must not be empty" in capsys.readouterr().err
####


@pytest.mark.parametrize("option", ("--include", "--exclude"))
def test_cli_rejects_empty_discovery_patterns(
        option: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as error:
        cli.main([option, "", str(tmp_path)])
    ####

    assert error.value.code == 2
    assert "must not be empty" in capsys.readouterr().err
####


@pytest.mark.parametrize(
    ("arguments", "message"),
    (
        (("--preset", "unknown"), "unknown preset"),
        (("--select", "statement.unknown"), "unknown selector"),
    ),
)
def test_cli_validates_policy_options_without_python_files(
        arguments: tuple[str, str], message: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()

    assert cli.main([*arguments, "--quiet", str(empty)]) == 2
    assert message in capsys.readouterr().err
####


def test_cli_validates_invalid_config_without_python_files(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    config = tmp_path / "scope-markers.toml"
    config.write_text('select = ["statement.unknown"]\n', encoding="utf-8")

    assert cli.main(["--config", str(config), "--quiet", str(empty)]) == 2
    assert "unknown selector" in capsys.readouterr().err
####


def test_cli_preflights_nested_policies_before_rewriting_any_file(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    valid = tmp_path / "valid.py"
    nested = tmp_path / "nested"
    nested.mkdir()
    invalid = nested / "invalid.py"
    valid_source = "def valid():\n    pass\n"
    invalid_source = "def invalid():\n    pass\n"
    valid.write_text(valid_source, encoding="utf-8")
    invalid.write_text(invalid_source, encoding="utf-8")
    (nested / "scope-markers.toml").write_text(
        'select = ["statement.unknown"]\n', encoding="utf-8"
    )

    assert cli.main(["--fix", "--quiet", str(tmp_path)]) == 2
    assert valid.read_text(encoding="utf-8") == valid_source
    assert invalid.read_text(encoding="utf-8") == invalid_source
    assert "unknown selector" in capsys.readouterr().err
####


def test_cli_entry_point_is_registered_and_module_is_usable() -> None:
    registered = {
        entry.name: entry.value for entry in entry_points(group="console_scripts")
    }
    assert registered["scope-markers"] == "scope_markers.cli:main"

    project_root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        path
        for path in (str(project_root / "src"), environment.get("PYTHONPATH"))
        if path
    )
    completed = subprocess.run(
        [sys.executable, "-m", "scope_markers", "--version"],
        cwd=project_root,
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert completed.returncode == 0
    assert completed.stdout.strip() == f"scope-markers {scope_markers.__version__}"
####


def test_check_fix_and_diff_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "example.py"
    path.write_text("def example():\n    pass\n", encoding="utf-8")

    assert cli.main([str(path)]) == 1
    assert "needs markers:" in capsys.readouterr().out
    assert cli.main(["--diff", str(path)]) == 1
    diff_output = capsys.readouterr().out
    assert "@@" in diff_output
    assert "+####" in diff_output
    assert cli.main(["--fix", "--quiet", str(path)]) == 0
    assert cli.main(["--quiet", str(path)]) == 0
####


def test_cli_strip_supports_check_diff_and_fix(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "example.py"
    path.write_text("if enabled:\n    pass\n####\n", encoding="utf-8")

    assert cli.main(["--strip", str(path)]) == 1
    assert f"markers to strip: {path}" in capsys.readouterr().out

    assert cli.main(["--strip", "--diff", str(path)]) == 1
    assert "-####" in capsys.readouterr().out

    assert cli.main(["--strip", "--fix", "--quiet", str(path)]) == 0
    assert path.read_text(encoding="utf-8") == "if enabled:\n    pass\n"
    assert cli.main(["--strip", "--quiet", str(path)]) == 0
####


def test_cli_strip_accepts_invalid_python_and_stub_files(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    invalid = tmp_path / "invalid.py"
    invalid.write_text("not valid Python\n####\n", encoding="utf-8")
    assert cli.main(["--strip", "--fix", "--quiet", str(invalid)]) == 0
    assert invalid.read_text(encoding="utf-8") == "not valid Python\n"

    stub = tmp_path / "interfaces.pyi"
    stub.write_text("def example() -> None: ...\n####\n", encoding="utf-8")
    assert cli.main(["--strip", "--mark-stubs", "--fix", "--quiet", str(stub)]) == 0
    assert stub.read_text(encoding="utf-8") == "def example() -> None: ...\n"
    assert capsys.readouterr().out == ""
####


def test_cli_strip_ignores_invalid_policy_configuration(tmp_path: Path) -> None:
    path = tmp_path / "invalid.py"
    path.write_text("not valid Python: ####\n####\n", encoding="utf-8")
    (tmp_path / "scope-markers.toml").write_text(
        'select = ["statement.not-a-selector"]\n', encoding="utf-8"
    )

    assert cli.main(["--strip", "--fix", "--quiet", str(path)]) == 0
    assert path.read_text(encoding="utf-8") == "not valid Python: ####\n"
####


def test_cli_strip_diff_rejects_changed_bare_cr_files(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "bare-cr.py"
    path.write_bytes(b"value = 1\r####\r")

    assert cli.main(["--strip", "--diff", str(path)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "bare-CR line endings" in captured.err
####


def test_cli_rejects_indent_normalization_while_stripping(
        capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exception:
        cli.main(["--strip", "--indent-width", "2"])
    ####

    assert exception.value.code == 2
    assert "--indent-width cannot be used with --strip" in capsys.readouterr().err
####


def test_cli_fix_reports_fixed_files_unless_quiet(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "example.py"
    path.write_text("def example():\n    pass\n", encoding="utf-8")

    assert cli.main(["--fix", str(path)]) == 0
    assert f"fixed: {path}" in capsys.readouterr().out

    path.write_text("def example():\n    pass\n", encoding="utf-8")
    assert cli.main(["--fix", "--quiet", str(path)]) == 0
    assert capsys.readouterr().out == ""
####


def test_cli_defaults_to_the_current_directory(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "example.py").write_text("def example():\n    pass\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert cli.main([]) == 1
    assert "needs markers: example.py" in capsys.readouterr().out
####


def test_cli_version_option_exits_with_version(
        capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exception:
        cli.main(["--version"])
    ####

    assert exception.value.code == 0
    assert capsys.readouterr().out.strip() == f"scope-markers {scope_markers.__version__}"
####


def test_cli_help_option_lists_supported_options(
        capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exception:
        cli.main(["--help"])
    ####

    output = capsys.readouterr().out
    assert exception.value.code == 0
    for option in (
            "--fix",
            "--diff",
            "--strip",
            "--mark-stubs",
            "--indent-width",
            "--quiet",
            "--verbose",
            "--fail-fast",
            "--no-default-excludes",
            "--include",
            "--exclude",
            "--version",
    ):
        assert option in output
    ####
    assert "default mode checks files without changing them" in output
    assert "file or directory to inspect" in output
    assert "examples:" in output
####


def test_cli_rejects_conflicting_fix_and_diff_options(
        capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exception:
        cli.main(["--fix", "--diff"])
    ####

    assert exception.value.code == 2
    assert "argument --diff: not allowed with argument --fix" in capsys.readouterr().err
####


def test_cli_rejects_unknown_arguments_with_usage_error(
        capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exception:
        cli.main(["--not-a-real-option"])
    ####

    assert exception.value.code == 2
    assert "unrecognized arguments: --not-a-real-option" in capsys.readouterr().err
####


def test_cli_rejects_options_missing_values(
        capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exception:
        cli.main(["--include"])
    ####

    assert exception.value.code == 2
    assert "argument --include: expected one argument" in capsys.readouterr().err
####


def test_cli_rejects_non_positive_indent_width(
        capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exception:
        cli.main(["--indent-width", "0"])
    ####

    assert exception.value.code == 2
    assert "argument --indent-width: must be a positive integer" in capsys.readouterr().err
####


def test_cli_verbose_reports_status_without_polluting_diff(
        tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "example.py"
    path.write_text("def example():\n    pass\n", encoding="utf-8")

    assert cli.main(["--diff", "--verbose", str(path)]) == 1
    captured = capsys.readouterr()

    assert "+####" in captured.out
    assert f"needs markers: {path}" in captured.err

    assert cli.main(["--fix", "--verbose", str(path)]) == 0
    assert f"fixed: {path}" in capsys.readouterr().out
####


def test_display_path_escapes_output_control_characters() -> None:
    path = Path("line\nbreak" + chr(9) + "\u202ename.py")

    assert _paths.display_path(path) == r"line\nbreak\t\u202ename.py"
####


def test_cli_fail_fast_stops_after_the_first_changed_file(tmp_path: Path) -> None:
    first = tmp_path / "a.py"
    second = tmp_path / "b.py"
    for path in (first, second):
        path.write_text("def example():\n    pass\n", encoding="utf-8")
    ####

    assert cli.main(["--fail-fast", "--fix", "--quiet", str(tmp_path)]) == 0
    assert first.read_text(encoding="utf-8").endswith("####\n")
    assert not second.read_text(encoding="utf-8").endswith("####\n")
####


def test_cli_fail_fast_check_reports_only_the_first_change(
        tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    first = tmp_path / "a.py"
    second = tmp_path / "b.py"
    for path in (first, second):
        path.write_text("def example():\n    pass\n", encoding="utf-8")
    ####

    assert cli.main(["--fail-fast", "--verbose", str(tmp_path)]) == 1
    output = capsys.readouterr().out

    assert f"needs markers: {first}" in output
    assert f"needs markers: {second}" not in output
####


def test_cli_fail_fast_stops_after_the_first_processing_error(
        tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    broken = tmp_path / "a_broken.py"
    valid = tmp_path / "b_valid.py"
    broken.write_text("def broken(:\n", encoding="utf-8")
    valid.write_text("def valid():\n    pass\n", encoding="utf-8")

    assert cli.main(["--fail-fast", "--verbose", str(tmp_path)]) == 2
    captured = capsys.readouterr()

    assert str(broken) in captured.err
    assert str(valid) not in captured.out
####


def test_cli_fail_fast_reports_discovery_errors_before_fixing_files(
        tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    missing = tmp_path / "missing.py"
    valid = tmp_path / "valid.py"
    original = "def valid():\n    pass\n"
    valid.write_text(original, encoding="utf-8")

    assert cli.main(["--fail-fast", "--fix", str(missing), str(valid)]) == 2

    assert valid.read_text(encoding="utf-8") == original
    assert str(missing) in capsys.readouterr().err
####


def test_cli_fix_summary_reports_actual_changes_and_idempotency(
        tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "example.py"
    path.write_text("def example():\n    pass\n", encoding="utf-8")

    assert cli.main(["--fix", str(path)]) == 0
    first_output = capsys.readouterr().out
    assert "scope markers fixed (1 files)" in first_output

    assert cli.main(["--fix", str(path)]) == 0
    second_output = capsys.readouterr().out
    assert "scope markers already clean (1 files)" in second_output
####


def test_cli_reports_missing_path_as_error(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "missing"

    assert cli.main([str(missing)]) == 2
    assert "path does not exist" in capsys.readouterr().err
####


def test_syntax_error_reports_line_and_column(tmp_path: Path) -> None:
    path = tmp_path / "broken.py"
    path.write_text("def broken(:\n", encoding="utf-8")

    changed, error = scope_markers.process_file(path, fix=False)

    assert changed is False
    assert error is not None
    assert f"{path}:" in error
####


def test_formatter_is_idempotent_on_its_own_source() -> None:
    path = Path(scope_markers.__file__).resolve()
    source = path.read_text(encoding="utf-8")

    assert scope_markers.format_source(source, filename=str(path)) == source
####


def test_script_runs_as_a_standalone_cli(tmp_path: Path) -> None:
    path = tmp_path / "example.py"
    path.write_text("def example():\n    pass\n", encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, "-m", "scope_markers", "--fix", "--quiet", str(path)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert path.read_text(encoding="utf-8").endswith("####\n")
####

from __future__ import annotations

import os
import stat
import subprocess
import sys
from contextlib import suppress
from importlib.metadata import entry_points
from importlib.metadata import version as installed_version
from pathlib import Path

import pytest

import scope_markers as package
from scope_markers import api, cli
from scripts import check_black, ci

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


def test_all_compound_statement_families_are_supported() -> None:
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
    )

    formatted = scope_markers.format_source(source)

    assert formatted.count("####") == 12
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
        "    ####\n"
        "    case 2 if ready:\n"
        "        pass\n"
        "    ####\n"
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
        ("python311", "-m", "ruff", "check", "."),
        ("python311", "-m", "flake8", "src", "scripts", "tests"),
        ("python311", "scripts/check_black.py"),
        ("python311", "-m", "pyright"),
        ("python311", "-m", "build", "--wheel"),
        ("scope-markers", "."),
    )
####


def test_ci_fix_mode_adds_safe_formatter_fix_flags() -> None:
    assert ci.ci_commands("python311", fix=True) == (
        ("python311", "-m", "pytest", "-q"),
        ("python311", "-m", "ruff", "check", "--fix", "."),
        ("python311", "-m", "flake8", "src", "scripts", "tests"),
        ("python311", "scripts/check_black.py"),
        ("python311", "-m", "pyright"),
        ("python311", "-m", "build", "--wheel"),
        ("scope-markers", "--fix", "."),
    )
####


def test_ci_main_runs_all_commands_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    commands = (("first",), ("second",), ("third",))
    called: list[tuple[str, ...]] = []
    monkeypatch.setattr(ci, "ci_commands", lambda: commands)
    monkeypatch.setattr(ci, "run_command", lambda command: called.append(command) or 0)

    assert ci.main() == 0
    assert called == list(commands)
####


def test_ci_main_forwards_fix_option(monkeypatch: pytest.MonkeyPatch) -> None:
    received: list[bool] = []
    monkeypatch.setattr(
        ci,
        "ci_commands",
        lambda fix=False: received.append(fix) or (),
    )
    monkeypatch.setattr(ci, "run_command", lambda command: 0)

    assert ci.main(["--fix"]) == 0
    assert received == [True]
####


def test_ci_run_command_reports_startup_errors(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail_to_start(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
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
    tmp_dir: Path,
) -> None:
    source = (
        "def first(values: list[int]) -> list[int]:\n"
        "    return values[1 : 2]\n"
        "####\n"
        "def second() -> None:\n"
        "    pass\n"
    )
    path = tmp_dir / "marked.py"
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
        "#####\n"
        "#### explanation\n"
        "value = 1  # ####\n"
        "def example() -> None:\n"
        "    pass\n"
    )

    formatted = scope_markers.format_source(source)

    assert "#####\n" in formatted
    assert "#### explanation\n" in formatted
    assert "value = 1  # ####\n" in formatted
    assert formatted.count("\n####\n") == 1
####


def test_two_hash_marker_style_is_detected_and_preserved() -> None:
    source = "def example() -> None:\n    pass\n##\n"

    assert scope_markers.format_source(source) == "def example() -> None:\n    pass\n##\n"
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

    with pytest.raises(ValueError, match="conflicting standalone marker styles"):
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


def test_inconsistent_tab_and_space_indentation_is_reported(tmp_dir: Path) -> None:
    path = tmp_dir / "inconsistent.py"
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


def test_non_utf8_source_encoding_and_cookie_are_preserved(tmp_dir: Path) -> None:
    path = tmp_dir / "latin1.py"
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


def test_cp1252_source_encoding_is_supported(tmp_dir: Path) -> None:
    path = tmp_dir / "cp1252.py"
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


def test_utf8_bom_is_preserved(tmp_dir: Path) -> None:
    path = tmp_dir / "bom.py"
    path.write_bytes(b"\xef\xbb\xbfdef example():\n    pass\n")

    assert scope_markers.process_file(path, fix=True) == (True, None)
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")
####


@pytest.mark.skipif(os.name == "nt", reason="Windows does not expose Unix executable bits")
def test_atomic_fix_preserves_executable_bits(tmp_dir: Path) -> None:
    path = tmp_dir / "tool.py"
    path.write_text("def main():\n    pass\n", encoding="utf-8")
    path.chmod(0o751)

    assert scope_markers.process_file(path, fix=True) == (True, None)
    assert stat.S_IMODE(path.stat().st_mode) == 0o751
####


def test_explicit_symlink_updates_target_without_replacing_link(tmp_dir: Path) -> None:
    if not hasattr(os, "symlink"):
        pytest.skip("symlinks are unavailable")
    ####
    target = tmp_dir / "target.py"
    link = tmp_dir / "link.py"
    target.write_text("def example():\n    pass\n", encoding="utf-8")
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation is not permitted")
    ####

    assert scope_markers.process_file(link, fix=True) == (True, None)
    assert link.is_symlink()
    assert target.read_text(encoding="utf-8").endswith("####\n")
####


def test_recursive_discovery_skips_symlinked_files_and_generated_directories(
        tmp_dir: Path,
) -> None:
    source = tmp_dir / "source.py"
    source.write_text("pass\n", encoding="utf-8")
    generated = tmp_dir / ".venv"
    generated.mkdir()
    (generated / "ignored.py").write_text("pass\n", encoding="utf-8")
    link = tmp_dir / "linked.py"
    with suppress(OSError):
        link.symlink_to(source)
    ####

    files, errors = scope_markers.discover_python_files([tmp_dir])

    assert files == [source]
    assert errors == []
####


def test_discovery_reports_missing_and_non_python_explicit_paths(tmp_dir: Path) -> None:
    text = tmp_dir / "notes.txt"
    text.write_text("notes", encoding="utf-8")

    files, errors = scope_markers.discover_python_files([tmp_dir / "missing", text])

    assert files == []
    assert len(errors) == 2
    assert "does not exist" in errors[0]
    assert "expected a .py file" in errors[1]
####


def test_legacy_python_files_api_deduplicates_and_sorts(tmp_dir: Path) -> None:
    first = tmp_dir / "a.py"
    second = tmp_dir / "b.py"
    first.write_text("pass\n", encoding="utf-8")
    second.write_text("pass\n", encoding="utf-8")

    assert scope_markers.python_files([second, first, second]) == [first, second]
####


def test_discovery_prunes_generated_directories_recursively(tmp_dir: Path) -> None:
    source = tmp_dir / "src" / "module.py"
    source.parent.mkdir()
    source.write_text("pass\n", encoding="utf-8")
    ignored = tmp_dir / "build" / "module.py"
    ignored.parent.mkdir()
    ignored.write_text("pass\n", encoding="utf-8")

    files, errors = scope_markers.discover_python_files([tmp_dir])

    assert files == [source]
    assert errors == []
####


def test_discovery_skips_an_explicit_symlinked_directory_root(tmp_dir: Path) -> None:
    target = tmp_dir / "target"
    target.mkdir()
    (target / "module.py").write_text("pass\n", encoding="utf-8")
    link = tmp_dir / "linked-root"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is not permitted")
    ####

    files, errors = scope_markers.discover_python_files([link])

    assert files == []
    assert errors == []
####


def test_discovery_skips_a_generated_directory_when_it_is_the_root(tmp_dir: Path) -> None:
    generated = tmp_dir / "build"
    generated.mkdir()
    source = generated / "module.py"
    source.write_text("pass\n", encoding="utf-8")

    files, errors = scope_markers.discover_python_files([generated])

    assert files == []
    assert errors == []
####


def test_discovery_treats_generated_directory_names_case_insensitively(
        tmp_dir: Path,
) -> None:
    generated = tmp_dir / "BUILD"
    generated.mkdir()
    (generated / "module.py").write_text("pass\n", encoding="utf-8")

    files, errors = scope_markers.discover_python_files([tmp_dir])

    assert files == []
    assert errors == []
####


def test_discovery_skips_a_root_inside_a_generated_directory(
        tmp_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    generated = tmp_dir / ".venv"
    nested = generated / "package"
    nested.mkdir(parents=True)
    (nested / "module.py").write_text("pass\n", encoding="utf-8")
    monkeypatch.chdir(nested)

    files, errors = scope_markers.discover_python_files([Path(".")])

    assert files == []
    assert errors == []
####


def test_discovery_can_disable_default_directory_exclusions(tmp_dir: Path) -> None:
    generated = tmp_dir / ".venv"
    generated.mkdir()
    source = generated / "module.py"
    source.write_text("pass\n", encoding="utf-8")

    files, errors = scope_markers.discover_python_files(
        [generated], use_default_excludes=False
    )

    assert files == [source]
    assert errors == []
####


def test_discovery_skips_egg_info_directories_by_default(tmp_dir: Path) -> None:
    metadata = tmp_dir / "scope_markers.egg-info"
    metadata.mkdir()
    source = metadata / "generated.py"
    source.write_text("pass\n", encoding="utf-8")

    files, errors = scope_markers.discover_python_files([tmp_dir])

    assert files == []
    assert errors == []
####


def test_discovery_supports_multiple_roots_and_exclude_patterns(tmp_dir: Path) -> None:
    first = tmp_dir / "first"
    second = tmp_dir / "second"
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


def test_discovery_include_patterns_allow_python_compatible_extensions(tmp_dir: Path) -> None:
    starlark = tmp_dir / "BUILD.bzl"
    starlark.write_text("def rule():\n    pass\n", encoding="utf-8")

    files, errors = scope_markers.discover_python_files([tmp_dir])
    assert files == []
    assert errors == []

    files, errors = scope_markers.discover_python_files(
        [tmp_dir], include_patterns=("*.bzl",)
    )

    assert files == [starlark]
    assert errors == []
    assert cli.main(["--include", "*.bzl", "--fix", "--quiet", str(tmp_dir)]) == 0
    assert starlark.read_text(encoding="utf-8").endswith("####\n")
####


def test_cli_mark_stubs_option_is_forwarded(tmp_dir: Path) -> None:
    path = tmp_dir / "stub.py"
    path.write_text("def example() -> None: ...\n", encoding="utf-8")

    assert cli.main(["--mark-stubs", str(path)]) == 1
    assert cli.main(["--mark-stubs", "--fix", "--quiet", str(path)]) == 0
    assert path.read_text(encoding="utf-8").endswith("####\n")
####


def test_cli_accepts_multiple_roots_and_exclude_patterns(tmp_dir: Path) -> None:
    first = tmp_dir / "first.py"
    second_root = tmp_dir / "second"
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


def test_cli_default_excludes_can_be_disabled(tmp_dir: Path) -> None:
    generated = tmp_dir / ".uv-cache"
    generated.mkdir()
    source = generated / "module.py"
    source.write_text("def example():\n    pass\n", encoding="utf-8")

    assert cli.main(["--fix", "--quiet", str(tmp_dir)]) == 0
    assert not source.read_text(encoding="utf-8").endswith("####\n")

    assert cli.main(
        ["--no-default-excludes", "--fix", "--quiet", str(tmp_dir)]
    ) == 0
    assert source.read_text(encoding="utf-8").endswith("####\n")
####


def test_cli_supports_repeated_exclude_patterns(tmp_dir: Path) -> None:
    first = tmp_dir / "first.py"
    second = tmp_dir / "second.generated.py"
    first.write_text("def example():\n    pass\n", encoding="utf-8")
    second.write_text("def example():\n    pass\n", encoding="utf-8")

    assert cli.main(
        ["--exclude", "*.generated.py", "--exclude", "unused", str(tmp_dir)]
    ) == 1
    assert not first.read_text(encoding="utf-8").endswith("####\n")
    assert not second.read_text(encoding="utf-8").endswith("####\n")
####


def test_token_error_reports_line_and_column(tmp_dir: Path) -> None:
    path = tmp_dir / "unfinished.py"
    path.write_text('value = "unterminated\n', encoding="utf-8")

    changed, error = scope_markers.process_file(path, fix=False)

    assert changed is False
    assert error is not None
    assert f"{path}:" in error
####


def test_process_file_reports_missing_input_file(tmp_dir: Path) -> None:
    path = tmp_dir / "missing.py"

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
    assert api.discover_python_files is scope_markers.discover_python_files
    assert issubclass(api.ScopeMarkersError, ValueError)
####


def test_programmatic_api_surface_is_complete_and_usable(tmp_dir: Path) -> None:
    assert api.__all__ == (
        "FileInspection",
        "ScopeBoundary",
        "ScopeMarkersError",
        "__version__",
        "discover_python_files",
        "format_source",
        "inspect_file",
        "process_file",
        "python_files",
    )
    assert api.__version__ == installed_version("scope-markers")

    path = tmp_dir / "example.py"
    path.write_text("def example():\n    pass\n", encoding="utf-8")
    inspection = api.inspect_file(path)

    assert isinstance(inspection, api.FileInspection)
    assert inspection.path == path
    assert inspection.changed is True
    assert api.format_source(inspection.source) == inspection.formatted
    assert api.process_file(path, fix=False) == (True, None)
    assert api.process_file(path, fix=True) == (True, None)
    assert api.process_file(path, fix=False) == (False, None)

    starlark = tmp_dir / "BUILD.bzl"
    starlark.write_text("def rule():\n    pass\n", encoding="utf-8")
    discovered, errors = api.discover_python_files(
        [tmp_dir], include_patterns=("*.bzl",), exclude_patterns=("example.py",)
    )

    assert discovered == [starlark]
    assert errors == []
    assert api.python_files([starlark], include_patterns=("*.bzl",)) == [starlark]

    boundary = api.ScopeBoundary(0, "", 0, 1)
    assert boundary.line_number == 1
####


def test_console_script_is_registered_and_usable() -> None:
    registered = {
        entry.name: entry.value for entry in entry_points(group="console_scripts")
    }
    assert registered["scope-markers"] == "scope_markers.cli:main"

    completed = subprocess.run(
        ["scope-markers", "--version"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert completed.stdout.strip() == f"scope-markers {scope_markers.__version__}"
####


def test_check_fix_and_diff_exit_codes(tmp_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_dir / "example.py"
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


def test_cli_diff_marks_a_missing_final_newline(
        tmp_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_dir / "no-final-newline.py"
    path.write_bytes(b"def example():\n    pass")

    assert cli.main(["--diff", str(path)]) == 1
    output = capsys.readouterr().out

    assert "-    pass\n\\ No newline at end of file\n+    pass\n" in output
    assert "-    pass+    pass" not in output
####


def test_cli_diff_normalizes_bare_carriage_return_lines(
        tmp_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_dir / "bare-cr.py"
    path.write_bytes(b"def example():\r    pass\r")

    assert cli.main(["--diff", str(path)]) == 1
    output = capsys.readouterr().out

    assert "    pass\n+####\n" in output
    assert "\r" not in output
####


def test_cli_diff_normalizes_mixed_line_endings(
        tmp_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_dir / "mixed-newlines.py"
    path.write_bytes(b"def first():\r\n    pass\r\ndef second():\n    pass\n")

    assert cli.main(["--diff", str(path)]) == 1
    output = capsys.readouterr().out

    assert "\r" not in output
    assert "-    pass+    pass" not in output
    assert output.count("+####\n") == 2
####


def test_cli_fix_reports_fixed_files_unless_quiet(
        tmp_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_dir / "example.py"
    path.write_text("def example():\n    pass\n", encoding="utf-8")

    assert cli.main(["--fix", str(path)]) == 0
    assert f"fixed: {path}" in capsys.readouterr().out

    path.write_text("def example():\n    pass\n", encoding="utf-8")
    assert cli.main(["--fix", "--quiet", str(path)]) == 0
    assert capsys.readouterr().out == ""
####


def test_cli_defaults_to_the_current_directory(
        tmp_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_dir / "example.py").write_text("def example():\n    pass\n", encoding="utf-8")
    monkeypatch.chdir(tmp_dir)

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
            "--mark-stubs",
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


def test_cli_verbose_reports_status_without_polluting_diff(
        tmp_dir: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_dir / "example.py"
    path.write_text("def example():\n    pass\n", encoding="utf-8")

    assert cli.main(["--diff", "--verbose", str(path)]) == 1
    captured = capsys.readouterr()

    assert "+####\n" in captured.out
    assert f"needs markers: {path}" in captured.err

    assert cli.main(["--fix", "--verbose", str(path)]) == 0
    assert f"fixed: {path}" in capsys.readouterr().out
####


def test_cli_fail_fast_stops_after_the_first_changed_file(tmp_dir: Path) -> None:
    first = tmp_dir / "a.py"
    second = tmp_dir / "b.py"
    for path in (first, second):
        path.write_text("def example():\n    pass\n", encoding="utf-8")
    ####

    assert cli.main(["--fail-fast", "--fix", "--quiet", str(tmp_dir)]) == 0
    assert first.read_text(encoding="utf-8").endswith("####\n")
    assert not second.read_text(encoding="utf-8").endswith("####\n")
####


def test_cli_fail_fast_check_reports_only_the_first_change(
        tmp_dir: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    first = tmp_dir / "a.py"
    second = tmp_dir / "b.py"
    for path in (first, second):
        path.write_text("def example():\n    pass\n", encoding="utf-8")
    ####

    assert cli.main(["--fail-fast", "--verbose", str(tmp_dir)]) == 1
    output = capsys.readouterr().out

    assert f"needs markers: {first}" in output
    assert f"needs markers: {second}" not in output
####


def test_cli_fail_fast_stops_after_the_first_processing_error(
        tmp_dir: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    broken = tmp_dir / "a_broken.py"
    valid = tmp_dir / "b_valid.py"
    broken.write_text("def broken(:\n", encoding="utf-8")
    valid.write_text("def valid():\n    pass\n", encoding="utf-8")

    assert cli.main(["--fail-fast", "--verbose", str(tmp_dir)]) == 2
    captured = capsys.readouterr()

    assert str(broken) in captured.err
    assert str(valid) not in captured.out
####


def test_cli_reports_missing_path_as_error(
        tmp_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_dir / "missing"

    assert cli.main([str(missing)]) == 2
    assert "path does not exist" in capsys.readouterr().err
####


def test_syntax_error_reports_line_and_column(tmp_dir: Path) -> None:
    path = tmp_dir / "broken.py"
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


def test_script_runs_as_a_standalone_cli(tmp_dir: Path) -> None:
    path = tmp_dir / "example.py"
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

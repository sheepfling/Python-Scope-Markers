from __future__ import annotations

import os
import stat
import subprocess
import sys
from importlib.metadata import entry_points
from importlib.metadata import version as installed_version
from pathlib import Path

import pytest

import scope_markers
from scripts import ci


def test_nested_scopes_are_closed_inside_out() -> None:
    source = (
        "class Example:\n"
        "    def method(self, value: int) -> int:\n"
        "        if value > 0:\n"
        "            return value\n"
        "        else:\n"
        "            return -value\n"
    )

    assert scope_markers.format_source(source) == (
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

    assert formatted.count("####") == 10
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


def test_match_cases_are_clauses_not_separate_marked_statements() -> None:
    source = (
        "match value:\n"
        "    case 1:\n"
        "        pass\n"
        "    case 2 if ready:\n"
        "        pass\n"
        "    case _:\n"
        "        pass\n"
    )

    assert scope_markers.format_source(source).count("####") == 1
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


def test_ci_command_list_is_explicit_and_uses_the_requested_python() -> None:
    assert ci.ci_commands("python311") == (
        ("python311", "-m", "pytest", "-q"),
        ("python311", "-m", "ruff", "check", "."),
        ("python311", "-m", "pyright"),
        ("python311", "-m", "build", "--wheel"),
        ("python311", "scope_markers.py", "scripts"),
        ("scope-markers", "."),
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


def test_formfeed_indentation_is_preserved() -> None:
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


def test_explicit_symlink_updates_target_without_replacing_link(tmp_path: Path) -> None:
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

    assert scope_markers.process_file(link, fix=True) == (True, None)
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
    try:
        link.symlink_to(source)
    except OSError:
        link = Path("missing")
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
    assert "expected a .py file" in errors[1]
####


def test_legacy_python_files_api_deduplicates_and_sorts(tmp_path: Path) -> None:
    first = tmp_path / "a.py"
    second = tmp_path / "b.py"
    first.write_text("pass\n", encoding="utf-8")
    second.write_text("pass\n", encoding="utf-8")

    assert scope_markers.python_files([second, first, second]) == [first, second]
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


def test_cli_mark_stubs_option_is_forwarded(tmp_path: Path) -> None:
    path = tmp_path / "stub.py"
    path.write_text("def example() -> None: ...\n", encoding="utf-8")

    assert scope_markers.main(["--mark-stubs", str(path)]) == 1
    assert scope_markers.main(["--mark-stubs", "--fix", "--quiet", str(path)]) == 0
    assert path.read_text(encoding="utf-8").endswith("####\n")
####


def test_token_error_reports_line_and_column(tmp_path: Path) -> None:
    path = tmp_path / "unfinished.py"
    path.write_text('value = "unterminated\n', encoding="utf-8")

    changed, error = scope_markers.process_file(path, fix=False)

    assert changed is False
    assert error is not None
    assert f"{path}:" in error
####


def test_version_is_loaded_from_installed_metadata() -> None:
    assert scope_markers.__version__ == installed_version("scope-markers")
####


def test_console_script_is_registered_and_usable() -> None:
    registered = {
        entry.name: entry.value for entry in entry_points(group="console_scripts")
    }
    assert registered["scope-markers"] == "scope_markers:main"

    completed = subprocess.run(
        ["scope-markers", "--version"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert completed.stdout.strip() == f"scope-markers {scope_markers.__version__}"
####


def test_check_fix_and_diff_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "example.py"
    path.write_text("def example():\n    pass\n", encoding="utf-8")

    assert scope_markers.main([str(path)]) == 1
    assert scope_markers.main(["--diff", str(path)]) == 1
    diff_output = capsys.readouterr().out
    assert "@@" in diff_output
    assert "+####" in diff_output
    assert scope_markers.main(["--fix", "--quiet", str(path)]) == 0
    assert scope_markers.main(["--quiet", str(path)]) == 0
####


def test_cli_reports_missing_path_as_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "missing"

    assert scope_markers.main([str(missing)]) == 2
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
    script = Path(scope_markers.__file__).resolve()

    completed = subprocess.run(
        [sys.executable, str(script), "--fix", "--quiet", str(path)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert path.read_text(encoding="utf-8").endswith("####\n")
####

from __future__ import annotations

from pathlib import Path

import pytest

from scope_markers import api, cli


def test_format_markdown_source_formats_python_fences_only() -> None:
    source = (
        "# Example\n"
        "\n"
        "```python\n"
        "def example():\n"
        "    if ready:\n"
        "        pass\n"
        "```\n"
        "\n"
        "```text\n"
        "def not_python():\n"
        "```\n"
        "\n"
        "~~~py\n"
        "class Other:\n"
        "    pass\n"
        "~~~\n"
    )

    formatted = api.format_markdown_source(source)

    assert formatted == (
        "# Example\n"
        "\n"
        "```python\n"
        "def example():\n"
        "    if ready:\n"
        "        pass\n"
        "    ####\n"
        "####\n"
        "```\n"
        "\n"
        "```text\n"
        "def not_python():\n"
        "```\n"
        "\n"
        "~~~py\n"
        "class Other:\n"
        "    pass\n"
        "####\n"
        "~~~\n"
    )
    assert api.format_markdown_source(formatted) == formatted
####


def test_format_markdown_source_preserves_indented_fence_prefix() -> None:
    source = (
        "  ```python\n"
        "  if ready:\n"
        "      pass\n"
        "  ```\n"
    )

    assert api.format_markdown_source(source) == (
        "  ```python\n"
        "  if ready:\n"
        "      pass\n"
        "  ####\n"
        "  ```\n"
    )
####


@pytest.mark.parametrize("newline", ("\n", "\r\n", "\r"))
def test_format_markdown_source_preserves_fence_newlines(newline: str) -> None:
    source = newline.join(("```python", "if ready:", "    pass", "```", ""))

    assert api.format_markdown_source(source) == newline.join(
        ("```python", "if ready:", "    pass", "####", "```", "")
    )
####


def test_format_markdown_source_can_strip_fenced_markers() -> None:
    source = "```python\ndef example():\n    pass\n####\n```\n"

    assert api.format_markdown_source(source, strip=True) == (
        "```python\ndef example():\n    pass\n```\n"
    )
####


@pytest.mark.parametrize(
    "option", ("no-scope-markers", "scope-markers: off", "scope-markers=ignore")
)
def test_format_markdown_source_preserves_opted_out_python_fences(option: str) -> None:
    source = f"```python {option}\nif ready:\n    pass\n```\n"

    assert api.format_markdown_source(source) == source
    assert api.format_markdown_source(source, strip=True) == source
####


def test_cli_markdown_mode_fixes_markdown_file(tmp_path: Path) -> None:
    path = tmp_path / "README.md"
    path.write_text("```python\ndef example():\n    pass\n```\n", encoding="utf-8")

    assert cli.main(["--markdown", "--fix", "--quiet", str(path)]) == 0
    assert path.read_text(encoding="utf-8") == (
        "```python\ndef example():\n    pass\n####\n```\n"
    )
####


def test_process_markdown_file_has_stable_check_and_fix_results(tmp_path: Path) -> None:
    path = tmp_path / "README.md"
    path.write_text("```python\ndef example():\n    pass\n```\n", encoding="utf-8")

    assert api.process_markdown_file(path, fix=False) == (True, None)
    assert api.process_markdown_file(path, fix=True) == (True, None)
    assert api.process_markdown_file(path, fix=False) == (False, None)
####


def test_markdown_files_are_discovered_only_when_requested(tmp_path: Path) -> None:
    path = tmp_path / "README.md"
    path.write_text("```python\npass\n```\n", encoding="utf-8")

    files, errors = api.discover_python_files([tmp_path])
    assert files == []
    assert errors == []

    files, errors = api.discover_python_files([tmp_path], include_markdown=True)
    assert files == [path]
    assert errors == []
####


def test_cli_does_not_process_markdown_without_markdown_mode(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "README.md"
    path.write_text("```python\ndef example():\n    pass\n```\n", encoding="utf-8")

    assert cli.main(["--fix", "--quiet", str(path)]) == 2
    assert "supported source file" in capsys.readouterr().err
####

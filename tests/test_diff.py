from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scope_markers import _diff, api, cli


def test_diff_uses_shared_root_for_external_paths() -> None:
    path = Path.cwd().parent / "external-tree" / "example.py"

    assert _diff._diff_path(  # pyright: ignore[reportPrivateUsage]
        path
    ) == "external-tree/example.py"
####


def test_cli_diff_uses_shared_root_without_git(
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
) -> None:
    original_directory = Path.cwd()
    project = tmp_path / "project"
    source_dir = project / "src"
    tests_dir = project / "tests"
    source_dir.mkdir(parents=True)
    tests_dir.mkdir()
    (tests_dir / "example.py").write_text(
        "def example():\n    pass\n", encoding="utf-8"
    )

    def no_repository_root(start: Path) -> None:
        return None
    ####

    monkeypatch.setattr(  # pyright: ignore[reportPrivateUsage]
        _diff, "_repository_root", no_repository_root
    )
    monkeypatch.chdir(source_dir)

    assert cli.main(["--diff", "../tests/example.py"]) == 1
    output = capsys.readouterr().out

    assert "--- a/tests/example.py\n" in output
    assert "+++ b/tests/example.py\n" in output
    monkeypatch.chdir(original_directory)
####


def test_diff_quotes_surrogateescaped_path_bytes() -> None:
    path = "a/\udcff.py"
    raw = os.fsencode(path)

    assert _diff._quote_diff_path(  # pyright: ignore[reportPrivateUsage]
        path
    ) == '"' + "".join(
        chr(byte) if 0x20 <= byte < 0x7F else f"\\{byte:03o}" for byte in raw
    ) + '"'
####


@pytest.mark.parametrize(
    ("filename", "header"),
    (
        ("space name.py", "--- a/space name.py\n"),
        ('quote"name.py', '--- "a/quote\\"name.py"\n'),
        ("tab\tname.py", '--- "a/tab\\tname.py"\n'),
        ("line\nbreak.py", '--- "a/line\\nbreak.py"\n'),
        ("emoji-😀.py", '--- "a/emoji-\\360\\237\\230\\200.py"\n'),
    ),
)
def test_diff_quotes_path_metadata_for_pathological_names(
        filename: str, header: str
) -> None:
    inspection = api.FileInspection(
        path=Path(filename),
        source="value = 1\n",
        formatted="value = 2\n",
        encoding="utf-8",
    )

    rendered = b"".join(_diff.render_diff(inspection))

    assert rendered.startswith(header.encode("utf-8"))
####


def test_cli_diff_keeps_clean_stdout_patch_only(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "clean.py"
    path.write_text("value = 1\n", encoding="utf-8")

    assert cli.main(["--diff", str(path)]) == 0
    captured = capsys.readouterr()

    assert captured.out == ""
    assert "scope markers clean" in captured.err
####


def test_cli_diff_marks_a_missing_final_newline(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "no-final-newline.py"
    path.write_bytes(b"def example():\n    pass")

    assert cli.main(["--diff", str(path)]) == 1
    output = capsys.readouterr().out

    assert "-    pass\n\\ No newline at end of file\n+    pass\n" in output
    assert "-    pass+    pass" not in output
####


def test_cli_diff_marks_missing_newline_on_unchanged_context_line(
        tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "context-no-final-newline.py"
    path.write_bytes(b"if x:\n    pass\nx = 1")

    assert cli.main(["--diff", str(path)]) == 1
    output = capsys.readouterr().out

    assert " x = 1\n\\ No newline at end of file\n" in output
####


def test_diff_eof_annotations_are_not_confused_with_header_lines() -> None:
    inspection = api.FileInspection(
        path=Path("example.py"),
        source="--old",
        formatted="++new",
        encoding="utf-8",
    )

    rendered = b"".join(_diff.render_diff(inspection))

    assert rendered.count(b"\\ No newline at end of file\n") == 2
####


def test_cli_diff_rejects_bare_carriage_return_lines(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "bare-cr.py"
    path.write_bytes(b"def example():\r    pass\r")

    assert cli.main(["--diff", str(path)]) == 2
    captured = capsys.readouterr()

    assert captured.out == ""
    assert "bare-CR line endings" in captured.err
####


def test_cli_diff_preserves_crlf_records_in_mixed_line_endings(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "mixed-newlines.py"
    path.write_bytes(b"def first():\r\n    pass\r\ndef second():\n    pass\n")

    assert cli.main(["--diff", str(path)]) == 1
    output = capsys.readouterr().out

    assert " def first():\r\n" in output
    assert "     pass\r\n" in output
    assert "+####\r\n" in output
    assert "+####\n" in output
    assert "-    pass+    pass" not in output
    assert output.count("+####") == 2
####


def test_cli_diff_for_crlf_file_is_acceptable_to_git(
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
) -> None:
    git = shutil.which("git")
    if git is None:
        pytest.skip("git is unavailable")
    ####

    repo = tmp_path / "repo"
    repo.mkdir()
    path = repo / "example.py"
    path.write_bytes(b"def example():\r\n    pass\r\n")
    subprocess.run([git, "init", "--quiet"], cwd=repo, check=True)
    monkeypatch.chdir(repo)

    assert cli.main(["--diff", str(path)]) == 1
    patch = tmp_path / "change.patch"
    patch.write_text(capsys.readouterr().out, encoding="utf-8", newline="")

    checked = subprocess.run(
        [git, "apply", "--check", str(patch)],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )

    assert checked.returncode == 0, checked.stderr
####


@pytest.mark.parametrize("argument", ("../tests/example.py", "ABSOLUTE"))
def test_cli_diff_uses_repository_relative_labels_from_subdirectories(
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        argument: str,
) -> None:
    git = shutil.which("git")
    if git is None:
        pytest.skip("git is unavailable")
    ####

    repo = tmp_path / "repo"
    source_dir = repo / "src"
    tests_dir = repo / "tests"
    source_dir.mkdir(parents=True)
    tests_dir.mkdir()
    path = tests_dir / "example.py"
    path.write_text("def example():\n    pass\n", encoding="utf-8")
    subprocess.run([git, "init", "--quiet"], cwd=repo, check=True)
    monkeypatch.chdir(source_dir)
    selected = str(path) if argument == "ABSOLUTE" else argument

    assert cli.main(["--diff", selected]) == 1
    output = capsys.readouterr().out
    assert "--- a/tests/example.py\n" in output
    assert "+++ b/tests/example.py\n" in output
    assert "a/../" not in output
    assert "b/../" not in output

    patch = tmp_path / "change.patch"
    patch.write_text(output, encoding="utf-8", newline="")
    checked = subprocess.run(
        [git, "apply", "--check", str(patch)],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
    )

    assert checked.returncode == 0, checked.stderr
####


@pytest.mark.parametrize(
    ("filename", "data"),
    (
        ("utf8.py", b"# coding: utf-8\ndef example():\n    value = 'h\xc3\xa9llo'\n"),
        ("cp1252.py", b"# coding: cp1252\ndef example():\n    value = 'h\xe9llo'\n"),
        ("bom.py", b"\xef\xbb\xbfdef example():\n    pass\n"),
    ),
)
def test_cli_diff_preserves_source_encoding_for_git(
        tmp_path: Path,
        filename: str,
        data: bytes,
) -> None:
    git = shutil.which("git")
    if git is None:
        pytest.skip("git is unavailable")
    ####

    repo = tmp_path / "repo"
    repo.mkdir()
    path = repo / filename
    path.write_bytes(data)
    subprocess.run([git, "init", "--quiet"], cwd=repo, check=True)

    completed = subprocess.run(
        [sys.executable, "-m", "scope_markers", "--diff", str(path)],
        cwd=repo,
        check=False,
        capture_output=True,
    )
    assert completed.returncode == 1
    patch = tmp_path / "change.patch"
    patch.write_bytes(completed.stdout)

    checked = subprocess.run(
        [git, "apply", "--check", str(patch)],
        cwd=repo,
        check=False,
        capture_output=True,
    )

    assert checked.returncode == 0, checked.stderr.decode(errors="replace")
####


def test_cli_diff_encodes_unicode_path_metadata_separately(
        tmp_path: Path,
) -> None:
    git = shutil.which("git")
    if git is None:
        pytest.skip("git is unavailable")
    ####

    repo = tmp_path / "repo"
    source_dir = repo / "emoji-😀"
    source_dir.mkdir(parents=True)
    path = source_dir / "example.py"
    path.write_bytes(b"# coding: cp1252\ndef example():\n    value = 'h\xe9llo'\n")
    subprocess.run([git, "init", "--quiet"], cwd=repo, check=True)

    completed = subprocess.run(
        [sys.executable, "-m", "scope_markers", "--diff", str(path)],
        cwd=repo,
        check=False,
        capture_output=True,
    )
    patch = tmp_path / "change.patch"
    patch.write_bytes(completed.stdout)

    checked = subprocess.run(
        [git, "apply", "--check", str(patch)],
        cwd=repo,
        check=False,
        capture_output=True,
    )

    assert completed.returncode == 1
    assert checked.returncode == 0, checked.stderr.decode(errors="replace")
####


def test_cli_diff_subprocess_preserves_crlf_bytes(tmp_path: Path) -> None:
    path = tmp_path / "example.py"
    path.write_bytes(b"def example():\r\n    pass\r\n")

    completed = subprocess.run(
        [sys.executable, "-m", "scope_markers", "--diff", path.name],
        cwd=tmp_path,
        check=False,
        capture_output=True,
    )

    assert completed.returncode == 1
    assert b"\r\r\n" not in completed.stdout
    assert b" def example():\r\n" in completed.stdout
    assert b"+####\r\n" in completed.stdout
####


def test_cli_diff_marks_missing_final_newline_in_mixed_line_endings(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Mixed physical endings must remain separate in a patch."""
    path = tmp_path / "mixed-no-final-newline.py"
    path.write_bytes(b"def first():\r\n    pass\r\ndef second():\n    pass")

    assert cli.main(["--diff", str(path)]) == 1
    output = capsys.readouterr().out

    assert " def first():\r\n" in output
    assert "-    pass+    pass" not in output
    assert "-    pass\n\\ No newline at end of file\n+    pass\n" in output
####

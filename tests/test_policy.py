from __future__ import annotations

from pathlib import Path

import pytest

from scope_markers import api, cli


@pytest.mark.parametrize(
    "preset", ("none", "definitions", "statements", "classic", "all")
)
def test_every_policy_preset_loads_and_expands(preset: str, tmp_path: Path) -> None:
    config = tmp_path / "scope-markers.toml"
    config.write_text(f'preset = "{preset}"\n', encoding="utf-8")

    policy = api.load_policy(config)

    expected = (
        frozenset[api.BoundaryKind]()
        if preset == "none"
        else api.expand_selectors((preset,))
    )
    assert policy.selected == expected
####


def test_all_preset_marks_every_match_case(tmp_path: Path) -> None:
    config = tmp_path / "scope-markers.toml"
    config.write_text('preset = "all"\n', encoding="utf-8")
    source = (
        "match value:\n"
        "    case 1:\n"
        "        handle_one()\n"
        "    case _:\n"
        "        handle_other()\n"
    )

    assert api.format_source(source, policy=api.load_policy(config)).count("####") == 3
####


@pytest.mark.parametrize(
    ("settings", "expected"),
    (
        (
            'preset = "definitions"\n',
            api.expand_selectors(("definitions",)),
        ),
        (
            'preset = "none"\nextend-select = ["statement.match"]\n',
            api.expand_selectors(("statement.match",)),
        ),
        (
            'preset = "classic"\nignore = ["clause.match.case"]\n',
            api.expand_selectors(("statements",)),
        ),
        (
            'select = ["statement.if"]\n'
            'extend-select = ["clause.if.else"]\n'
            'ignore = ["statement.if"]\n',
            api.expand_selectors(("clause.if.else",)),
        ),
        (
            'select = ["statement.if", "clause.if"]\n',
            api.expand_selectors(("conditionals",)),
        ),
    ),
)
def test_selector_replace_extend_ignore_combinations(
        settings: str, expected: frozenset[api.BoundaryKind], tmp_path: Path
) -> None:
    config = tmp_path / "scope-markers.toml"
    config.write_text(settings, encoding="utf-8")

    assert api.load_policy(config).selected == expected
####


def test_every_global_filter_is_loaded(tmp_path: Path) -> None:
    config = tmp_path / "scope-markers.toml"
    config.write_text(
        "skip-inline-suites = true\n"
        "min-span-lines = 2\n"
        "min-body-lines = 3\n"
        "min-body-statements = 4\n"
        "min-clauses = 5\n"
        "min-depth = 1\n"
        "max-depth = 6\n"
        'stub-policy = "mark"\n',
        encoding="utf-8",
    )

    policy = api.load_policy(config)

    assert policy.skip_inline_suites is True
    assert policy.min_span_lines == 2
    assert policy.min_body_lines == 3
    assert policy.min_body_statements == 4
    assert policy.min_clauses == 5
    assert policy.min_depth == 1
    assert policy.max_depth == 6
    assert policy.stub_policy == "mark"
####


def test_every_rule_filter_overrides_global_values(tmp_path: Path) -> None:
    config = tmp_path / "scope-markers.toml"
    config.write_text(
        "min-span-lines = 2\n"
        "min-body-lines = 2\n"
        "min-body-statements = 2\n"
        "min-clauses = 2\n"
        "min-depth = 1\n"
        "max-depth = 5\n"
        'stub-policy = "skip"\n'
        "[rules.\"statement.if\"]\n"
        "skip-inline-suites = true\n"
        "min-span-lines = 3\n"
        "min-body-lines = 4\n"
        "min-body-statements = 5\n"
        "min-clauses = 6\n"
        "min-depth = 2\n"
        "max-depth = 7\n"
        'stub-policy = "mark"\n'
        'require = ["has-else"]\n',
        encoding="utf-8",
    )

    rule = api.load_policy(config).rules[api.BoundaryKind.STATEMENT_IF]

    assert rule.skip_inline_suites is True
    assert rule.min_span_lines == 3
    assert rule.min_body_lines == 4
    assert rule.min_body_statements == 5
    assert rule.min_clauses == 6
    assert rule.min_depth == 2
    assert rule.max_depth == 7
    assert rule.stub_policy == "mark"
    assert rule.require == frozenset({"has-else"})
####


def test_per_file_override_applies_all_layers_in_order(tmp_path: Path) -> None:
    config = tmp_path / "scope-markers.toml"
    source = tmp_path / "src" / "example.py"
    source.parent.mkdir()
    config.write_text(
        'preset = "definitions"\n'
        "[rules.\"statement.function\"]\n"
        "min-body-lines = 2\n"
        "\n"
        "[[per-file]]\n"
        'patterns = ["src/**"]\n'
        'preset = "all"\n'
        'select = ["statement.if"]\n'
        'extend-select = ["clause.if.else"]\n'
        'ignore = ["statement.if"]\n'
        "skip-inline-suites = true\n"
        "min-span-lines = 3\n"
        "min-body-lines = 4\n"
        "min-body-statements = 5\n"
        "min-clauses = 6\n"
        "min-depth = 1\n"
        "max-depth = 7\n"
        'stub-policy = "mark"\n'
        "[per-file.rules.\"clause.if.else\"]\n"
        'require = ["nested"]\n',
        encoding="utf-8",
    )
    source.write_text("if ready:\n    work()\nelse:\n    recover()\n", encoding="utf-8")

    policy = api.resolve_policy(config, source)
    rule = policy.rules[api.BoundaryKind.CLAUSE_IF_ELSE]

    assert policy.selected == frozenset({api.BoundaryKind.CLAUSE_IF_ELSE})
    assert policy.skip_inline_suites is True
    assert policy.min_span_lines == 3
    assert policy.min_body_lines == 4
    assert policy.min_body_statements == 5
    assert policy.min_clauses == 6
    assert policy.min_depth == 1
    assert policy.max_depth == 7
    assert policy.stub_policy == "mark"
    assert rule.require == frozenset({"nested"})
####


def test_per_file_preset_preserves_accumulated_selector_arithmetic(tmp_path: Path) -> None:
    config = tmp_path / "scope-markers.toml"
    source = tmp_path / "src" / "example.py"
    source.parent.mkdir()
    config.write_text(
        'preset = "classic"\n'
        'extend-select = ["clause.if.else"]\n'
        'ignore = ["statement.if"]\n'
        "\n"
        "[[per-file]]\n"
        'patterns = ["src/**"]\n'
        'preset = "statements"\n',
        encoding="utf-8",
    )
    source.write_text("if ready:\n    work()\nelse:\n    recover()\n", encoding="utf-8")

    policy = api.resolve_policy(config, source)

    assert api.BoundaryKind.STATEMENT_IF not in policy.selected
    assert api.BoundaryKind.CLAUSE_IF_ELSE in policy.selected
####


def test_cli_overrides_configuration_for_every_policy_layer(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = tmp_path / "scope-markers.toml"
    source = tmp_path / "example.py"
    config.write_text(
        'preset = "definitions"\n'
        "min-span-lines = 1\n"
        'stub-policy = "skip"\n',
        encoding="utf-8",
    )
    source.write_text("if ready:\n    work()\nelse:\n    recover()\n", encoding="utf-8")

    assert cli.main(
        [
            "--config",
            str(config),
            "--preset",
            "none",
            "--select",
            "statement.if",
            "--extend-select",
            "clause.if.else",
            "--ignore",
            "statement.if",
            "--skip-inline-suites",
            "--min-span-lines",
            "2",
            "--min-body-lines",
            "3",
            "--min-body-statements",
            "4",
            "--min-clauses",
            "5",
            "--min-depth",
            "1",
            "--max-depth",
            "6",
            "--mark-stubs",
            "--show-settings",
            str(source),
        ]
    ) == 0

    output = capsys.readouterr().out
    assert "select = [clause.if.else]" in output
    assert "skip-inline-suites = true" in output
    assert "min-span-lines = 2" in output
    assert "min-body-lines = 3" in output
    assert "min-body-statements = 4" in output
    assert "min-clauses = 5" in output
    assert "min-depth = 1" in output
    assert "max-depth = 6" in output
    assert "stub-policy = mark" in output
####

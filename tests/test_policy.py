from __future__ import annotations

from pathlib import Path

import pytest

from scope_markers import api, cli

_TIER_SOURCE = (
    "def standalone() -> None:\n"
    "    pass\n"
    "class Example:\n"
    "    def method(self) -> None:\n"
    "        pass\n"
    "if ready:\n"
    "    work()\n"
    "else:\n"
    "    recover()\n"
    "match value:\n"
    "    case 1:\n"
    "        one()\n"
    "    case _:\n"
    "        other()\n"
)


@pytest.mark.parametrize(
    "preset", ("none", "definitions", "logic", "statements", "all")
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


def test_classic_preset_name_is_rejected_after_consolidation(tmp_path: Path) -> None:
    config = tmp_path / "scope-markers.toml"
    config.write_text('preset = "classic"\n', encoding="utf-8")

    with pytest.raises(api.PolicyError, match="unknown preset 'classic'"):
        api.load_policy(config)
    ####
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


def test_logic_preset_marks_control_flow_without_definitions(tmp_path: Path) -> None:
    config = tmp_path / "scope-markers.toml"
    config.write_text('preset = "logic"\n', encoding="utf-8")
    source = (
        "def helper() -> None:\n"
        "    pass\n"
        "if ready:\n"
        "    work()\n"
        "else:\n"
        "    recover()\n"
        "match value:\n"
        "    case 1:\n"
        "        handle_one()\n"
        "    case _:\n"
        "        handle_other()\n"
    )

    formatted = api.format_source(source, policy=api.load_policy(config))

    assert formatted.count("####") == 3
    assert "    pass\nif ready:" in formatted
    assert formatted.endswith("        handle_other()\n    ####\n####\n")
####


def test_method_selector_distinguishes_class_methods_from_functions() -> None:
    source = (
        "def standalone() -> None:\n"
        "    pass\n"
        "class Example:\n"
        "    def method(self) -> None:\n"
        "        pass\n"
    )
    function_policy = api.MarkerPolicy(
        selected=api.expand_selectors(("statement.function",))
    )
    method_policy = api.MarkerPolicy(
        selected=api.expand_selectors(("statement.method",))
    )

    function_kinds = tuple(
        explanation.kind
        for explanation in api.explain_source(source, policy=function_policy)
        if explanation.will_mark
    )
    method_kinds = tuple(
        explanation.kind
        for explanation in api.explain_source(source, policy=method_policy)
        if explanation.will_mark
    )

    assert function_kinds == (api.BoundaryKind.STATEMENT_FUNCTION,)
    assert method_kinds == (api.BoundaryKind.STATEMENT_METHOD,)
    assert api.expand_selectors(("definitions",)) >= {
        api.BoundaryKind.STATEMENT_FUNCTION,
        api.BoundaryKind.STATEMENT_METHOD,
        api.BoundaryKind.STATEMENT_CLASS,
    }
####


@pytest.mark.parametrize(
    ("preset", "marker_count"),
    (
        ("definitions", 3),
        ("logic", 3),
        ("statements", 6),
        ("all", 8),
    ),
)
def test_preset_tiers_have_distinct_boundary_density(
        preset: str, marker_count: int, tmp_path: Path
) -> None:
    config = tmp_path / "scope-markers.toml"
    config.write_text(f'preset = "{preset}"\n', encoding="utf-8")
    policy = api.load_policy(config)
    explanations = api.explain_source(_TIER_SOURCE, policy=policy)
    marked_kinds = {explanation.kind for explanation in explanations if explanation.will_mark}

    assert api.format_source(_TIER_SOURCE, policy=policy).count("####") == marker_count
    if preset == "definitions":
        assert marked_kinds == {
            api.BoundaryKind.STATEMENT_FUNCTION,
            api.BoundaryKind.STATEMENT_METHOD,
            api.BoundaryKind.STATEMENT_CLASS,
        }
    elif preset == "logic":
        assert marked_kinds == {
            api.BoundaryKind.STATEMENT_IF,
            api.BoundaryKind.STATEMENT_MATCH,
            api.BoundaryKind.CLAUSE_MATCH_CASE,
        }
    elif preset == "statements":
        assert api.BoundaryKind.STATEMENT_METHOD in marked_kinds
        assert api.BoundaryKind.CLAUSE_MATCH_CASE in marked_kinds
    else:
        assert api.BoundaryKind.CLAUSE_IF_BODY in marked_kinds
        assert len(
            [
                explanation
                for explanation in explanations
                if explanation.kind is api.BoundaryKind.CLAUSE_MATCH_CASE
                and explanation.will_mark
            ]
        ) == 2
    ####
####


@pytest.mark.parametrize(
    ("settings", "expected_selectors", "marker_count"),
    (
        (
            'preset = "definitions"\n'
            'extend-select = ["statement.if"]\n',
            api.expand_selectors(("definitions", "statement.if")),
            4,
        ),
        (
            'preset = "logic"\n'
            'extend-select = ["statement.method"]\n',
            api.expand_selectors(("logic", "statement.method")),
            4,
        ),
        (
            'preset = "statements"\n'
            'ignore = ["statement.method"]\n',
            api.expand_selectors(("statements",)) - {
                api.BoundaryKind.STATEMENT_METHOD
            },
            5,
        ),
        (
            'preset = "all"\n'
            'ignore = ["clause.if", "clause.match.case"]\n',
            api.expand_selectors(("all",))
            - api.expand_selectors(("clause.if", "clause.match.case")),
            5,
        ),
        (
            'select = ["statement.method"]\n',
            api.expand_selectors(("statement.method",)),
            1,
        ),
        (
            'select = ["clause.match.case"]\n',
            api.expand_selectors(("clause.match.case",)),
            2,
        ),
        (
            'select = ["all"]\n',
            api.expand_selectors(("all",)),
            8,
        ),
    ),
)
def test_selector_composition_matrix(
        settings: str,
        expected_selectors: frozenset[api.BoundaryKind],
        marker_count: int,
        tmp_path: Path,
) -> None:
    config = tmp_path / "scope-markers.toml"
    config.write_text(settings, encoding="utf-8")

    policy = api.load_policy(config)

    assert policy.selected == expected_selectors
    assert api.format_source(_TIER_SOURCE, policy=policy).count("####") == marker_count
####


def test_statements_preset_combines_final_case_constraint_with_rule_filters(
        tmp_path: Path,
) -> None:
    config = tmp_path / "scope-markers.toml"
    config.write_text(
        'preset = "statements"\n'
        "\n"
        '[rules."clause.match.case"]\n'
        "min-body-lines = 1\n",
        encoding="utf-8",
    )
    source = (
        "match value:\n"
        "    case 1:\n"
        "        handle_one()\n"
        "    case _:\n"
        "        handle_other()\n"
    )

    assert api.format_source(source, policy=api.load_policy(config)).count("####") == 2
####


@pytest.mark.parametrize("selection", ("all", "clause.match.case"))
def test_explicit_selection_does_not_inherit_final_case_filter(
        selection: str, tmp_path: Path
) -> None:
    config = tmp_path / "scope-markers.toml"
    config.write_text(f'select = ["{selection}"]\n', encoding="utf-8")
    source = (
        "match value:\n"
        "    case 1:\n"
        "        handle_one()\n"
        "    case _:\n"
        "        handle_other()\n"
    )

    policy = api.load_policy(config)

    assert policy.final_case_only is False
    assert api.format_source(source, policy=policy).count("####") == (
        3 if selection == "all" else 2
    )
####


def test_cli_preset_preserves_custom_match_case_rule(tmp_path: Path) -> None:
    config = tmp_path / "scope-markers.toml"
    source = tmp_path / "example.py"
    config.write_text(
        'preset = "statements"\n'
        "\n"
        '[rules."clause.match.case"]\n'
        "min-body-lines = 2\n",
        encoding="utf-8",
    )
    source.write_text(
        "match value:\n"
        "    case 1:\n"
        "        handle_one()\n"
        "    case _:\n"
        "        handle_other()\n",
        encoding="utf-8",
    )

    assert cli.main(["--config", str(config), "--preset", "all", "--fix", str(source)]) == 0
    assert source.read_text(encoding="utf-8").count("####") == 1
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
            'preset = "statements"\nignore = ["clause.match.case"]\n',
            api.expand_selectors(("complete-statements",)),
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
        'preset = "statements"\n'
        'extend-select = ["clause.if.else"]\n'
        'ignore = ["statement.if"]\n'
        "\n"
        '[rules."clause.match.case"]\n'
        "min-body-lines = 2\n"
        "\n"
        "[[per-file]]\n"
        'patterns = ["src/**"]\n'
        'preset = "all"\n',
        encoding="utf-8",
    )
    source.write_text("if ready:\n    work()\nelse:\n    recover()\n", encoding="utf-8")

    policy = api.resolve_policy(config, source)

    assert api.BoundaryKind.STATEMENT_IF not in policy.selected
    assert api.BoundaryKind.CLAUSE_IF_ELSE in policy.selected
    assert policy.rules[api.BoundaryKind.CLAUSE_MATCH_CASE].min_body_lines == 2
####


def test_per_file_select_replaces_default_match_case_filter(tmp_path: Path) -> None:
    config = tmp_path / "scope-markers.toml"
    source = tmp_path / "src" / "example.py"
    source.parent.mkdir()
    config.write_text(
        'preset = "statements"\n'
        "\n"
        "[[per-file]]\n"
        'patterns = ["src/**"]\n'
        'select = ["clause.match.case"]\n',
        encoding="utf-8",
    )
    source.write_text(
        "match value:\n"
        "    case 1:\n"
        "        handle_one()\n"
        "    case _:\n"
        "        handle_other()\n",
        encoding="utf-8",
    )

    policy = api.resolve_policy(config, source)

    assert policy.final_case_only is False
    assert api.format_source(source.read_text(encoding="utf-8"), policy=policy).count(
        "####"
    ) == 2
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

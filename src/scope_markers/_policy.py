"""Marker-selection policy, selector expansion, and TOML configuration."""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum
from fnmatch import fnmatchcase
from pathlib import Path
from types import MappingProxyType
from typing import Final, TypeVar, cast

_Setting = TypeVar("_Setting")


class PolicyError(ValueError):
    """Raised when marker-policy configuration is invalid."""
####


class BoundaryKind(StrEnum):
    """A supported kind of marker boundary."""

    STATEMENT_FUNCTION = "statement.function"
    STATEMENT_CLASS = "statement.class"
    STATEMENT_IF = "statement.if"
    STATEMENT_FOR = "statement.for"
    STATEMENT_WHILE = "statement.while"
    STATEMENT_WITH = "statement.with"
    STATEMENT_TRY = "statement.try"
    STATEMENT_MATCH = "statement.match"
    CLAUSE_IF_BODY = "clause.if.body"
    CLAUSE_IF_ELIF = "clause.if.elif"
    CLAUSE_IF_ELSE = "clause.if.else"
    CLAUSE_FOR_BODY = "clause.for.body"
    CLAUSE_FOR_ELSE = "clause.for.else"
    CLAUSE_WHILE_BODY = "clause.while.body"
    CLAUSE_WHILE_ELSE = "clause.while.else"
    CLAUSE_TRY_BODY = "clause.try.body"
    CLAUSE_TRY_EXCEPT = "clause.try.except"
    CLAUSE_TRY_ELSE = "clause.try.else"
    CLAUSE_TRY_FINALLY = "clause.try.finally"
    CLAUSE_MATCH_CASE = "clause.match.case"
####


def _empty_boundary_kind_set() -> frozenset[BoundaryKind]:
    return frozenset()
####


ALL_BOUNDARY_KINDS: Final[frozenset[BoundaryKind]] = frozenset(
    kind for kind in BoundaryKind
)
STATEMENT_BOUNDARY_KINDS: Final[frozenset[BoundaryKind]] = frozenset(
    kind for kind in ALL_BOUNDARY_KINDS if str(kind).startswith("statement.")
)
CLASSIC_BOUNDARY_KINDS: Final[frozenset[BoundaryKind]] = frozenset(
    (*STATEMENT_BOUNDARY_KINDS, BoundaryKind.CLAUSE_MATCH_CASE)
)

SELECTOR_GROUPS: Final[Mapping[str, frozenset[BoundaryKind]]] = MappingProxyType(
    {
        "all": ALL_BOUNDARY_KINDS,
        "classic": CLASSIC_BOUNDARY_KINDS,
        "definitions": frozenset(
            {BoundaryKind.STATEMENT_FUNCTION, BoundaryKind.STATEMENT_CLASS}
        ),
        "statements": STATEMENT_BOUNDARY_KINDS,
        "clauses": frozenset(
            kind for kind in ALL_BOUNDARY_KINDS if str(kind).startswith("clause.")
        ),
        "conditionals": frozenset(
            kind for kind in ALL_BOUNDARY_KINDS if str(kind).startswith("statement.if")
            or str(kind).startswith("clause.if.")
        ),
        "loops": frozenset(
            kind
            for kind in ALL_BOUNDARY_KINDS
            if str(kind).startswith(
                ("statement.for", "statement.while", "clause.for.", "clause.while.")
            )
        ),
        "contexts": frozenset({BoundaryKind.STATEMENT_WITH}),
        "exceptions": frozenset(
            kind
            for kind in ALL_BOUNDARY_KINDS
            if str(kind).startswith(("statement.try", "clause.try."))
        ),
        "patterns": frozenset({BoundaryKind.STATEMENT_MATCH, BoundaryKind.CLAUSE_MATCH_CASE}),
    }
)

PRESETS: Final[Mapping[str, frozenset[BoundaryKind]]] = MappingProxyType(
    {
        "none": frozenset(),
        "definitions": SELECTOR_GROUPS["definitions"],
        "statements": SELECTOR_GROUPS["statements"],
        "classic": CLASSIC_BOUNDARY_KINDS,
        "all": ALL_BOUNDARY_KINDS,
    }
)

_GENERIC_PREDICATES: Final = frozenset(
    {"nested", "module-level", "class-level", "function-level", "stub"}
)
_PREDICATES_BY_KIND: Final[Mapping[BoundaryKind, frozenset[str]]] = MappingProxyType(
    {
        BoundaryKind.STATEMENT_IF: _GENERIC_PREDICATES | {"has-elif", "has-else"},
        BoundaryKind.STATEMENT_TRY: _GENERIC_PREDICATES
        | {"multiple-handlers", "has-finally"},
        BoundaryKind.STATEMENT_MATCH: _GENERIC_PREDICATES | {"multiple-cases"},
        **{
            kind: _GENERIC_PREDICATES
            for kind in ALL_BOUNDARY_KINDS
            - {
                BoundaryKind.STATEMENT_IF,
                BoundaryKind.STATEMENT_TRY,
                BoundaryKind.STATEMENT_MATCH,
            }
        },
    }
)

_POLICY_KEYS: Final = frozenset(
    {
        "preset",
        "select",
        "extend-select",
        "ignore",
        "skip-inline-suites",
        "min-span-lines",
        "min-body-lines",
        "min-body-statements",
        "min-clauses",
        "min-depth",
        "max-depth",
        "stub-policy",
        "rules",
    }
)
_CONFIG_KEYS: Final = _POLICY_KEYS | {"per-file"}
_PER_FILE_KEYS: Final = _POLICY_KEYS | {"patterns"}
_RULE_KEYS: Final = _POLICY_KEYS - {"preset", "select", "extend-select", "ignore", "rules"}
_FILTER_KEYS: Final = frozenset(
    {
        "skip-inline-suites",
        "min-span-lines",
        "min-body-lines",
        "min-body-statements",
        "min-clauses",
        "min-depth",
        "max-depth",
        "stub-policy",
    }
)


@dataclass(frozen=True, slots=True)
class RuleOverride:
    """Optional filters that replace global settings for one boundary kind."""

    skip_inline_suites: bool | None = None
    min_span_lines: int | None = None
    min_body_lines: int | None = None
    min_body_statements: int | None = None
    min_clauses: int | None = None
    min_depth: int | None = None
    max_depth: int | None = None
    stub_policy: str | None = None
    require: frozenset[str] = frozenset()
####


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    """The result and human-readable reason for evaluating one candidate."""

    allowed: bool
    reason: str
####


@dataclass(frozen=True, slots=True)
class MarkerPolicy:
    """The resolved rule set that decides which candidates produce markers."""

    selected: frozenset[BoundaryKind]
    skip_inline_suites: bool = False
    min_span_lines: int = 1
    min_body_lines: int = 1
    min_body_statements: int = 1
    min_clauses: int = 1
    min_depth: int = 0
    max_depth: int | None = None
    stub_policy: str = "skip"
    rules: Mapping[BoundaryKind, RuleOverride] = field(
        default_factory=lambda: MappingProxyType({})
    )
    selector_extensions: frozenset[BoundaryKind] = field(
        default_factory=_empty_boundary_kind_set, repr=False, compare=False
    )
    selector_exclusions: frozenset[BoundaryKind] = field(
        default_factory=_empty_boundary_kind_set, repr=False, compare=False
    )

    def allows(
            self,
            kind: BoundaryKind,
            *,
            span_lines: int,
            suite_line_counts: tuple[int, ...],
            suite_statement_counts: tuple[int, ...],
            clause_count: int,
            depth: int,
            facts: frozenset[str],
            inline_suite: bool,
    ) -> bool:
        """Return whether one fully analyzed candidate should be rendered."""
        return self.decision(
            kind,
            span_lines=span_lines,
            suite_line_counts=suite_line_counts,
            suite_statement_counts=suite_statement_counts,
            clause_count=clause_count,
            depth=depth,
            facts=facts,
            inline_suite=inline_suite,
        ).allowed
    ####

    def decision(
            self,
            kind: BoundaryKind,
            *,
            span_lines: int,
            suite_line_counts: tuple[int, ...],
            suite_statement_counts: tuple[int, ...],
            clause_count: int,
            depth: int,
            facts: frozenset[str],
            inline_suite: bool,
    ) -> PolicyDecision:
        """Explain whether one fully analyzed candidate should be rendered."""
        if kind not in self.selected:
            return PolicyDecision(False, "selector is not enabled")
        ####
        rule = self.rules.get(kind, RuleOverride())
        stub_policy = rule.stub_policy or self.stub_policy
        if "stub" in facts and stub_policy == "skip":
            return PolicyDecision(False, "stub policy skips this definition")
        ####
        if not rule.require.issubset(facts):
            required = ", ".join(sorted(rule.require - facts))
            return PolicyDecision(False, f"missing required facts: {required}")
        ####
        skip_inline = _effective(rule.skip_inline_suites, self.skip_inline_suites)
        if skip_inline and inline_suite:
            return PolicyDecision(False, "inline suite is skipped")
        ####
        min_span_lines = _effective(rule.min_span_lines, self.min_span_lines)
        if span_lines < min_span_lines:
            return PolicyDecision(False, f"span is below min-span-lines ({min_span_lines})")
        ####
        min_body_lines = _effective(rule.min_body_lines, self.min_body_lines)
        if max(suite_line_counts, default=0) < min_body_lines:
            return PolicyDecision(
                False, f"body is below min-body-lines ({min_body_lines})"
            )
        ####
        min_body_statements = _effective(
            rule.min_body_statements, self.min_body_statements
        )
        if max(suite_statement_counts, default=0) < min_body_statements:
            return PolicyDecision(
                False,
                f"body is below min-body-statements ({min_body_statements})",
            )
        ####
        min_clauses = _effective(rule.min_clauses, self.min_clauses)
        if clause_count < min_clauses:
            return PolicyDecision(False, f"has fewer than min-clauses ({min_clauses})")
        ####
        min_depth = _effective(rule.min_depth, self.min_depth)
        if depth < min_depth:
            return PolicyDecision(False, f"depth is below min-depth ({min_depth})")
        ####
        max_depth = _effective(rule.max_depth, self.max_depth)
        if max_depth is not None and depth > max_depth:
            return PolicyDecision(False, f"depth exceeds max-depth ({max_depth})")
        ####
        return PolicyDecision(True, "selected")
    ####
####


@dataclass(frozen=True, slots=True)
class _PerFileOverride:
    """One ordered TOML override resolved relative to its configuration file."""

    patterns: tuple[str, ...]
    settings: Mapping[str, object]
####


@dataclass(frozen=True, slots=True)
class _PolicyConfiguration:
    """A base policy and the per-file overrides loaded from one TOML file."""

    policy: MarkerPolicy
    directory: Path
    overrides: tuple[_PerFileOverride, ...]
####


def _effective(override: _Setting | None, default: _Setting) -> _Setting:
    return default if override is None else override
####


def classic_policy(*, mark_stubs: bool = False) -> MarkerPolicy:
    """Return the compatibility policy that reproduces legacy formatting."""
    return MarkerPolicy(
        selected=CLASSIC_BOUNDARY_KINDS,
        stub_policy="mark" if mark_stubs else "skip",
    )
####


def expand_selectors(selectors: tuple[str, ...]) -> frozenset[BoundaryKind]:
    """Expand exact selector names, groups, and namespace prefixes."""
    expanded: set[BoundaryKind] = set()
    for selector in selectors:
        name = selector.strip().casefold()
        if not name:
            raise PolicyError("selector names must not be empty")
        ####
        group = SELECTOR_GROUPS.get(name)
        if group is not None:
            expanded.update(group)
            continue
        ####
        try:
            expanded.add(BoundaryKind(name))
            continue
        except ValueError:
            pass
        ####
        prefix = f"{name}."
        prefixed: set[BoundaryKind] = {
                kind for kind in ALL_BOUNDARY_KINDS if str(kind).startswith(prefix)
        }
        if prefixed:
            expanded.update(prefixed)
            continue
        ####
        suggestion = _selector_suggestion(name)
        message = f'unknown selector "{selector}"'
        if suggestion is not None:
            message += f'; did you mean "{suggestion}"?'
        ####
        raise PolicyError(message)
    ####
    return frozenset(expanded)
####


def _selector_suggestion(selector: str) -> str | None:
    candidates = sorted((*SELECTOR_GROUPS, *(str(kind) for kind in ALL_BOUNDARY_KINDS)))
    matches = [candidate for candidate in candidates if candidate.startswith(selector[:3])]
    return matches[0] if matches else None
####


def selector_values(values: tuple[str, ...]) -> tuple[str, ...]:
    """Split repeatable command-line selector values on commas."""
    return tuple(part.strip() for value in values for part in value.split(",") if part.strip())
####


def policy_from_mapping(settings: Mapping[str, object]) -> MarkerPolicy:
    """Build a strict policy from a ``[tool.scope-markers]`` TOML table."""
    _validate_settings(settings, _CONFIG_KEYS, "scope-markers setting")
    _per_file_overrides(settings)
    return _apply_settings(classic_policy(), settings)
####


def policy_with_cli_overrides(
        policy: MarkerPolicy,
        *,
        preset: str | None = None,
        select: tuple[str, ...] = (),
        extend_select: tuple[str, ...] = (),
        ignore: tuple[str, ...] = (),
        skip_inline_suites: bool | None = None,
        min_span_lines: int | None = None,
        min_body_lines: int | None = None,
        min_body_statements: int | None = None,
        min_clauses: int | None = None,
        min_depth: int | None = None,
        max_depth: int | None = None,
        mark_stubs: bool = False,
) -> MarkerPolicy:
    """Apply command-line policy values after TOML settings."""
    extensions: frozenset[BoundaryKind] = policy.selector_extensions
    exclusions: frozenset[BoundaryKind] = policy.selector_exclusions
    base_selection = policy.selected
    if preset is not None:
        if preset not in PRESETS:
            raise PolicyError(f"unknown preset {preset!r}; expected one of {', '.join(PRESETS)}")
        ####
        base_selection = PRESETS[preset]
        extensions = frozenset[BoundaryKind]()
        exclusions = frozenset[BoundaryKind]()
    ####
    if select:
        base_selection = expand_selectors(selector_values(select))
        extensions = frozenset[BoundaryKind]()
        exclusions = frozenset[BoundaryKind]()
    ####
    extensions |= expand_selectors(selector_values(extend_select))
    exclusions |= expand_selectors(selector_values(ignore))
    selected = (base_selection | extensions) - exclusions
    values: dict[str, object] = {
        "selected": selected,
        "selector_extensions": extensions,
        "selector_exclusions": exclusions,
    }
    for key, value in (
            ("skip_inline_suites", skip_inline_suites),
            ("min_span_lines", min_span_lines),
            ("min_body_lines", min_body_lines),
            ("min_body_statements", min_body_statements),
            ("min_clauses", min_clauses),
            ("min_depth", min_depth),
            ("max_depth", max_depth),
    ):
        if value is not None:
            values[key] = value
        ####
    ####
    if mark_stubs:
        values["stub_policy"] = "mark"
    ####
    updated = replace(policy, **values)
    _validate_policy(updated)
    return updated
####


def load_policy(config: Path | None) -> MarkerPolicy:
    """Load one explicit TOML configuration file or return the classic policy."""
    return _load_configuration(config).policy
####


def resolve_policy(config: Path | None, path: Path) -> MarkerPolicy:
    """Resolve one configuration's ordered per-file overrides for ``path``."""
    configuration = _load_configuration(config)
    policy = configuration.policy
    for override in configuration.overrides:
        if _matches_per_file_pattern(path, configuration.directory, override.patterns):
            policy = _apply_settings(policy, override.settings)
        ####
    ####
    return policy
####


def _load_configuration(config: Path | None) -> _PolicyConfiguration:
    if config is None:
        return _PolicyConfiguration(classic_policy(), Path.cwd(), ())
    ####
    try:
        with config.open("rb") as stream:
            document: object = tomllib.load(stream)
        ####
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise PolicyError(f"{config}: {error}") from error
    ####
    if config.name == "pyproject.toml":
        project = _table(document, f"{config} root")
        tool = project.get("tool")
        if tool is None:
            return _PolicyConfiguration(classic_policy(), config.resolve().parent, ())
        ####
        settings = _table(tool, f"{config} tool table").get("scope-markers")
    else:
        settings = document
    ####
    if settings is None:
        return _PolicyConfiguration(classic_policy(), config.resolve().parent, ())
    ####
    try:
        table = _table(settings, f"{config} scope-markers settings")
        return _PolicyConfiguration(
            policy_from_mapping(table),
            config.resolve().parent,
            _per_file_overrides(table),
        )
    except PolicyError as error:
        raise PolicyError(f"{config}: {error}") from error
    ####
####


def _apply_settings(policy: MarkerPolicy, settings: Mapping[str, object]) -> MarkerPolicy:
    extensions = policy.selector_extensions
    exclusions = policy.selector_exclusions
    base_selection = policy.selected
    if "preset" in settings:
        preset = _string(settings, "preset", "classic")
        if preset not in PRESETS:
            raise PolicyError(f"unknown preset {preset!r}; expected one of {', '.join(PRESETS)}")
        ####
        base_selection = PRESETS[preset]
    ####
    if "select" in settings:
        base_selection = expand_selectors(_string_array(settings, "select"))
    ####
    extensions |= expand_selectors(_string_array(settings, "extend-select"))
    exclusions |= expand_selectors(_string_array(settings, "ignore"))
    selected = (base_selection | extensions) - exclusions
    policy = _replace_filters(
        replace(
            policy,
            selected=selected,
            selector_extensions=extensions,
            selector_exclusions=exclusions,
        ),
        settings,
    )
    if "rules" not in settings:
        return policy
    ####
    rules = dict(policy.rules)
    rules.update(_rules_from_mapping(settings["rules"]))
    return replace(policy, rules=MappingProxyType(rules))
####


def _per_file_overrides(settings: Mapping[str, object]) -> tuple[_PerFileOverride, ...]:
    raw = settings.get("per-file")
    if raw is None:
        return ()
    ####
    if not isinstance(raw, list):
        raise PolicyError("per-file must be an array of tables")
    ####
    overrides: list[_PerFileOverride] = []
    for index, item in enumerate(cast(list[object], raw), start=1):
        table = _table(item, f"per-file override {index}")
        _validate_settings(table, _PER_FILE_KEYS, f"per-file override {index} setting")
        patterns = _string_array(table, "patterns")
        if not patterns:
            raise PolicyError(f"per-file override {index} requires at least one pattern")
        ####
        overrides.append(
            _PerFileOverride(
                patterns=patterns,
                settings=MappingProxyType(
                    {key: value for key, value in table.items() if key != "patterns"}
                ),
            )
        )
    ####
    return tuple(overrides)
####


def _matches_per_file_pattern(path: Path, directory: Path, patterns: tuple[str, ...]) -> bool:
    lexical = path.absolute()
    resolved = path.resolve(strict=False)
    try:
        lexical_relative = lexical.relative_to(directory).as_posix()
    except ValueError:
        lexical_relative = None
    ####
    candidates = [path.name, lexical.as_posix(), resolved.as_posix()]
    if lexical_relative is not None:
        candidates.append(lexical_relative)
    ####
    return any(
        fnmatchcase(candidate, pattern) for candidate in candidates for pattern in patterns
    )
####


def _validate_settings(
        settings: Mapping[str, object], allowed: frozenset[str], description: str
) -> None:
    unknown = set(settings) - allowed
    if unknown:
        raise PolicyError(f"unknown {description}: {min(unknown)!r}")
    ####
####


def find_config(start: Path) -> Path | None:
    """Find the nearest supported configuration, starting at ``start``."""
    lexical = start.absolute()
    directory = lexical if start.is_dir() else lexical.parent
    while True:
        for name in ("scope-markers.toml", ".scope-markers.toml", "pyproject.toml"):
            candidate = directory / name
            if candidate.is_file() and (
                    name != "pyproject.toml" or _has_scope_markers_table(candidate)
            ):
                return candidate
            ####
        ####
        if directory.parent == directory:
            return None
        ####
        directory = directory.parent
    ####
####


def _has_scope_markers_table(path: Path) -> bool:
    try:
        with path.open("rb") as stream:
            document: object = tomllib.load(stream)
        ####
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise PolicyError(f"{path}: {error}") from error
    ####
    project = _table(document, f"{path} root")
    tool = project.get("tool")
    return tool is not None and "scope-markers" in _table(tool, f"{path} tool table")
####


def describe_policy(policy: MarkerPolicy) -> str:
    """Render a stable, human-readable policy summary."""
    selectors = ", ".join(sorted(str(kind) for kind in policy.selected)) or "(none)"
    max_depth = "unlimited" if policy.max_depth is None else str(policy.max_depth)
    return "\n".join(
        (
            f"select = [{selectors}]",
            f"skip-inline-suites = {str(policy.skip_inline_suites).lower()}",
            f"min-span-lines = {policy.min_span_lines}",
            f"min-body-lines = {policy.min_body_lines}",
            f"min-body-statements = {policy.min_body_statements}",
            f"min-clauses = {policy.min_clauses}",
            f"min-depth = {policy.min_depth}",
            f"max-depth = {max_depth}",
            f"stub-policy = {policy.stub_policy}",
        )
    )
####


def list_selectors() -> str:
    """Render the supported presets, groups, and exact selector names."""
    lines = ["presets:", *[f"  {name}" for name in PRESETS], "groups:"]
    lines.extend(f"  {name}" for name in SELECTOR_GROUPS)
    lines.append("selectors:")
    lines.extend(f"  {kind}" for kind in sorted(ALL_BOUNDARY_KINDS, key=str))
    return "\n".join(lines)
####


def _replace_filters(policy: MarkerPolicy, values: Mapping[str, object]) -> MarkerPolicy:
    replacements: dict[str, object] = {}
    for key in _FILTER_KEYS:
        if key not in values:
            continue
        ####
        attribute = key.replace("-", "_")
        if key == "stub-policy":
            replacements[attribute] = _stub_policy(values[key])
        elif key == "skip-inline-suites":
            replacements[attribute] = _bool(values[key], key)
        elif key == "max-depth" and values[key] is None:
            replacements[attribute] = None
        else:
            replacements[attribute] = _non_negative_integer(values[key], key)
        ####
    ####
    updated = replace(policy, **replacements)
    _validate_policy(updated)
    return updated
####


def _rules_from_mapping(raw: object) -> dict[BoundaryKind, RuleOverride]:
    if raw is None:
        return {}
    ####
    rules: dict[BoundaryKind, RuleOverride] = {}
    for selector, values in _table(raw, "rules").items():
        kinds = expand_selectors((selector,))
        if len(kinds) != 1:
            raise PolicyError(f"rule {selector!r} must name one exact selector")
        ####
        rule_table = _table(values, f"rule {selector!r}")
        unknown = set(rule_table) - (_RULE_KEYS | {"require"})
        if unknown:
            raise PolicyError(f"unknown setting for rule {selector!r}: {min(unknown)!r}")
        ####
        rule_values = _replace_filters(MarkerPolicy(selected=frozenset()), rule_table)
        require = frozenset(_string_array(rule_table, "require"))
        kind = next(iter(kinds))
        invalid_predicates = require - _PREDICATES_BY_KIND[kind]
        if invalid_predicates:
            raise PolicyError(
                f"rule {selector!r} does not support predicate "
                f"{min(invalid_predicates)!r}"
            )
        ####
        rules[kind] = RuleOverride(
            skip_inline_suites=(
                rule_values.skip_inline_suites if "skip-inline-suites" in rule_table else None
            ),
            min_span_lines=(
                rule_values.min_span_lines if "min-span-lines" in rule_table else None
            ),
            min_body_lines=(
                rule_values.min_body_lines if "min-body-lines" in rule_table else None
            ),
            min_body_statements=(
                rule_values.min_body_statements
                if "min-body-statements" in rule_table
                else None
            ),
            min_clauses=rule_values.min_clauses if "min-clauses" in rule_table else None,
            min_depth=rule_values.min_depth if "min-depth" in rule_table else None,
            max_depth=rule_values.max_depth if "max-depth" in rule_table else None,
            stub_policy=rule_values.stub_policy if "stub-policy" in rule_table else None,
            require=require,
        )
    ####
    return rules
####


def _validate_policy(policy: MarkerPolicy) -> None:
    if policy.stub_policy not in {"skip", "mark"}:
        raise PolicyError("stub-policy must be 'skip' or 'mark'")
    ####
    if policy.max_depth is not None and policy.max_depth < policy.min_depth:
        raise PolicyError("max-depth must be greater than or equal to min-depth")
    ####
####


def _string(settings: Mapping[str, object], key: str, default: str) -> str:
    value = settings.get(key, default)
    if not isinstance(value, str):
        raise PolicyError(f"{key} must be a string")
    ####
    return value.casefold()
####


def _string_array(settings: Mapping[str, object], key: str) -> tuple[str, ...]:
    if key not in settings:
        return ()
    ####
    value = settings[key]
    if not isinstance(value, list):
        raise PolicyError(f"{key} must be an array of strings")
    ####
    strings: list[str] = []
    for item in cast(list[object], value):
        if not isinstance(item, str):
            raise PolicyError(f"{key} must be an array of strings")
        ####
        strings.append(item)
    ####
    return tuple(strings)
####


def _table(value: object, description: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise PolicyError(f"{description} must be a table")
    ####
    table: dict[str, object] = {}
    for key, item in cast(dict[object, object], value).items():
        if not isinstance(key, str):
            raise PolicyError(f"{description} keys must be strings")
        ####
        table[key] = item
    ####
    return table
####


def _bool(value: object, key: str) -> bool:
    if not isinstance(value, bool):
        raise PolicyError(f"{key} must be true or false")
    ####
    return value
####


def _non_negative_integer(value: object, key: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise PolicyError(f"{key} must be a non-negative integer")
    ####
    return value
####


def _stub_policy(value: object) -> str:
    if not isinstance(value, str) or value.casefold() not in {"skip", "mark"}:
        raise PolicyError("stub-policy must be 'skip' or 'mark'")
    ####
    return value.casefold()
####

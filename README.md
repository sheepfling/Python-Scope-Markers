# Scope Markers

[![CI][ci-badge]][ci]
[![Python 3.11-3.14][python-badge]][python]
[![Runtime dependencies: none][deps-badge]][pyproject]

**Explicit visual endings for Python's indented compound statements.**

Scope Markers is an opinionated, standard-library-only Python formatter that inserts
standalone `####` comments at selected compound-statement and clause boundaries.

It can apply one consistent convention everywhere, or use a fine-grained policy based on
AST structure, body size, nesting depth, file patterns, and statement-specific predicates.
It can also format Python code inside Markdown fences.

Scope Markers is deterministic, idempotent, reversible with `--strip`, and guarded by an
AST-equivalence check. Its markers are ordinary Python comments and have no runtime effect.

## What it does

- marks complete functions, classes, conditionals, loops, context managers, exception
  handlers, and pattern matches;
- optionally marks individual `if`, loop, `try`, and `match case` suites;
- supports density presets from definitions-only through every available clause;
- filters markers by inline layout, line span, statement count, clause count, and depth;
- supports strict project configuration, per-selector rules, and ordered per-file overrides;
- formats standalone `python`, `py`, and `python3` Markdown fences with `--markdown`;
- supports file and next-boundary opt-out directives;
- checks, diffs, fixes, or strips markers without runtime dependencies.

## Example

```diff
 def absolute(value: int) -> int:
     if value < 0:
         return -value
+    ####
     return value
+####
```

A marker's indentation identifies the statement it closes. Unlike `# end if` or
`# end function`, `####` copies no name or clause label that can become stale. Scope
Markers removes recognized managed markers and regenerates their canonical placement from
parsed source.

This is a project convention, not a claim about universal Python style. Use it where
visible closing boundaries make code easier for your team to scan.

## Installation

Scope Markers requires Python 3.11 or newer.

Install directly from the repository with `uv`:

```bash
uv tool install git+https://github.com/sheepfling/Python-Scope-Markers.git
```

Or with `pipx`:

```bash
pipx install git+https://github.com/sheepfling/Python-Scope-Markers.git
```

For a one-off invocation:

```bash
uvx --from git+https://github.com/sheepfling/Python-Scope-Markers.git \
    scope-markers --diff .
```

From a cloned checkout, use `uv tool install .`, `pipx install .`, or
`python -m pip install -e .` inside a virtual environment.

The installed command and module entry point are equivalent:

```bash
scope-markers --help
python -m scope_markers --help
```

## Quick start

Check files without modifying them:

```bash
scope-markers .
```

Inspect or apply the proposed changes:

```bash
scope-markers --diff .
scope-markers --fix .
```

Remove managed markers:

```bash
scope-markers --strip --diff .
scope-markers --strip --fix .
```

Format eligible Python fences in Markdown:

```bash
scope-markers --markdown --diff README.md docs
scope-markers --markdown --fix README.md docs
```

The default invocation is check mode. It reports files that need changes, returns status
`1`, and leaves the files untouched.

## Choose a marker density

The built-in presets cover the common policies:

| Preset | Boundaries selected |
|---|---|
| `none` | No generated markers |
| `definitions` | Complete functions and classes |
| `statements` | Every complete compound statement, without internal clauses |
| `classic` | Complete compound statements plus every `match case` |
| `all` | Every supported statement and clause boundary |

`classic` is the default and preserves the original Scope Markers convention.

```bash
scope-markers --preset definitions --fix src
scope-markers --preset statements --fix src
scope-markers --preset classic --ignore clause.match.case --fix src
```

## Marker policy

A policy has three independent layers:

1. **Selection** chooses which kinds of boundaries are eligible.
2. **Shape filters** decide how substantial a candidate must be.
3. **Overrides** specialize a selector or a set of matching files.

This avoids a separate boolean option for every Python statement form.

### Boundary selectors

`statement.*` selectors close a complete compound statement:

| Selector | Boundary |
|---|---|
| `statement.function` | Complete `def` or `async def` |
| `statement.class` | Complete `class` |
| `statement.if` | Complete `if` / `elif` / `else` chain |
| `statement.for` | Complete `for` or `async for`, including `else` |
| `statement.while` | Complete `while`, including `else` |
| `statement.with` | Complete `with` or `async with` |
| `statement.try` | Complete `try`, handlers, `else`, and `finally` |
| `statement.match` | Complete `match` |

`clause.*` selectors close one suite within a compound statement:

| Selector | Boundary |
|---|---|
| `clause.if.body` | Initial `if` suite |
| `clause.if.elif` | Each `elif` suite |
| `clause.if.else` | Final `else` suite |
| `clause.for.body` | Primary `for` or `async for` suite |
| `clause.for.else` | Loop `else` suite |
| `clause.while.body` | Primary `while` suite |
| `clause.while.else` | Loop `else` suite |
| `clause.try.body` | Initial `try` suite |
| `clause.try.except` | Each `except` or `except*` suite |
| `clause.try.else` | `try`-`else` suite |
| `clause.try.finally` | `finally` suite |
| `clause.match.case` | Each `case` suite |

Selectors may be exact names, groups, or namespace prefixes. The groups are
`definitions`, `statements`, `clauses`, `conditionals`, `loops`, `contexts`,
`exceptions`, and `patterns`.

For example, `clause.if` expands to every `clause.if.*` selector:

```bash
scope-markers --select clause.if --diff src
```

Use `--list-selectors` to print the selectors, groups, and presets supported by the
installed version.

### Selection arithmetic

Selection is resolved in this order:

1. `preset` establishes the base policy.
2. `select` replaces the preset selection when present.
3. `extend-select` adds selectors.
4. `ignore` subtracts selectors.

For example:

```toml
[tool.scope-markers]
preset = "statements"
ignore = ["statement.if"]
extend-select = ["clause.if.else"]
```

This marks complete compound statements except complete `if` chains, while still marking
the final `else` suite when one exists.

Unknown settings, selectors, predicates, and values are errors rather than silent no-ops.

### Shape filters

Shape filters are objective and independent:

| Setting | Meaning |
|---|---|
| `skip-inline-suites` | Skip suites whose body begins on the header line |
| `min-span-lines` | Minimum physical span from candidate header through its end |
| `min-body-lines` | Minimum physical-line span of an owned suite |
| `min-body-statements` | Minimum direct AST statements in an owned suite |
| `min-clauses` | Minimum number of suites owned by the candidate |
| `min-depth` | Minimum compound-statement nesting depth |
| `max-depth` | Maximum compound-statement nesting depth |
| `stub-policy` | `skip` or `mark` docstring-only and ellipsis-only functions |

These filters answer different questions. A multiline call can occupy several physical
lines while remaining one direct statement:

```python
if ready:
    run(
        first,
        second,
    )
####
```

`min-body-lines = 2` may keep that boundary. `min-body-statements = 2` skips it.

### Project configuration

Configure Scope Markers in `pyproject.toml`:

```toml
[tool.scope-markers]
preset = "statements"
skip-inline-suites = true
min-body-lines = 2
stub-policy = "skip"

[tool.scope-markers.rules."statement.function"]
min-body-lines = 1

[tool.scope-markers.rules."statement.if"]
require = ["has-else"]

[[tool.scope-markers.per-file]]
patterns = ["tests/**"]
extend-select = ["clause.match.case"]

[[tool.scope-markers.per-file]]
patterns = ["tests/unit/**"]
min-body-lines = 1
```

The complete accepted configuration shape is:

```toml
[tool.scope-markers]
preset = "classic"                  # none, definitions, statements, classic, all
# select = ["definitions"]          # replace the preset selection
extend-select = ["clause.if"]       # add selectors, groups, or prefixes
ignore = ["clause.match.case"]      # subtract selectors
skip-inline-suites = true
min-span-lines = 2
min-body-lines = 2
min-body-statements = 1
min-clauses = 1
min-depth = 0
max-depth = 4
stub-policy = "skip"                # skip or mark
```

A selector-specific rule inherits every global value it does not override:

```toml
[tool.scope-markers.rules."statement.if"]
min-body-lines = 1
require = ["has-else"]
```

Supported predicates include:

| Applies to | Predicates |
|---|---|
| General candidates | `nested`, `module-level`, `class-level`, `function-level`, `stub` |
| `statement.if` | `has-elif`, `has-else` |
| `statement.try` | `multiple-handlers`, `has-finally` |
| `statement.match` | `multiple-cases` |

`require` is valid only inside a selector rule.

### Per-file policy

Each `[[tool.scope-markers.per-file]]` table requires one or more `patterns` and may
contain the global filters, `preset`, `select`, `extend-select`, `ignore`, and selector
rules.

Patterns are matched relative to the configuration file and also against the basename and
absolute path. Matching tables are applied in declaration order. Later scalar settings
replace earlier values; `extend-select` and `ignore` remain additive and subtractive.

```toml
[[tool.scope-markers.per-file]]
patterns = ["generated/**", "vendor/**"]
preset = "none"

[[tool.scope-markers.per-file]]
patterns = ["tests/**"]
extend-select = ["clause.match.case"]
ignore = ["statement.if"]
```

A policy exclusion still reads the file. Use `--exclude` when the path should not be
discovered or processed at all.

### Configuration discovery and inspection

For each processed file, the CLI finds the nearest `scope-markers.toml`,
`.scope-markers.toml`, or `pyproject.toml` containing `[tool.scope-markers]`.

Use:

```bash
scope-markers --config path/to/pyproject.toml src
scope-markers --isolated src
scope-markers --show-settings src/example.py
scope-markers --explain src/example.py
```

- `--config PATH` forces one configuration file.
- `--isolated` ignores discovered configuration.
- `--show-settings PATH` prints the resolved policy for one path.
- `--explain PATH` reports every candidate and why it is marked or skipped.

Command-line policy settings override configuration.

### Common policy recipes

Definitions only:

```toml
[tool.scope-markers]
preset = "definitions"
```

Complete statements without branch or case markers:

```toml
[tool.scope-markers]
preset = "statements"
```

Classic behavior without individual `case` markers:

```toml
[tool.scope-markers]
preset = "classic"
ignore = ["clause.match.case"]
```

Only final `else` suites:

```toml
[tool.scope-markers]
select = ["clause.if.else"]
```

Only substantial `if` chains with a final `else`:

```toml
[tool.scope-markers]
select = ["statement.if"]
skip-inline-suites = true
min-body-lines = 2
min-body-statements = 2

[tool.scope-markers.rules."statement.if"]
require = ["has-else"]
```

## Markdown code fences

Markdown support is opt-in. Scope Markers does not reflow or lint Markdown; it formats
Python source inside eligible fenced blocks.

```bash
scope-markers --markdown README.md docs
scope-markers --markdown --diff README.md docs
scope-markers --markdown --fix README.md docs
scope-markers --markdown --strip --fix README.md docs
```

Only standalone fences labeled `python`, `py`, or `python3` are processed. Other Markdown
content and non-Python fences remain unchanged. Each eligible fence must be valid as a
standalone Python source fragment; one fence cannot continue a class or function from
another fence.

For example, this Markdown:

````text
```python
def load(path: str) -> str:
    with open(path, encoding="utf-8") as stream:
        return stream.read()
```
````

becomes:

````markdown
```python
def load(path: str) -> str:
    with open(path, encoding="utf-8") as stream:
        return stream.read()
    ####
####
```
````

Unterminated outer fences are preserved rather than partially rewritten.

### Literal and instructional examples

An eligible Python fence that intentionally demonstrates unformatted source needs an
opt-out directive as its first non-empty line:

````markdown
```python
# scope-markers: off
if ready:
    run()
```
````

The equivalent `# no-scope-markers` and `# scope-markers=ignore` comments are also
accepted in Markdown fences. Keep the directive inside the code block rather than in the
fence info string.

For documentation that should not display a directive, use a `text` or `diff` fence, or
place the nested example inside a longer outer fence. This keeps the README itself stable
when checked with `scope-markers --markdown`.

An opted-out Markdown fence remains untouched, including during `--strip`.

## Source directives

### Disable one Python file

Place this comment on the first non-empty line:

```python
# scope-markers: off

def generated_module_entry() -> None:
    pass
```

Normal marker formatting leaves the file untouched.

### Ignore the next boundary

Place `ignore-next` immediately before the selected scope. Decorators may follow the
directive. Nested candidates remain eligible:

```python
# scope-markers: ignore-next
@generated
class GeneratedContainer:
    def useful_helper(self) -> None:
        pass
    ####
```

This suppresses the class boundary but retains the function boundary.

There is currently no range-based `off` / `on` directive. Use a per-file policy for a
generated or vendor tree.

## Discovery and file types

With no paths, the current directory is scanned recursively. Multiple files and
directories may be supplied.

Recursive discovery prunes common VCS, environment, cache, dependency, and build trees,
including `.git`, `.venv`, `.uv-cache`, `.cache`, `.pytest_cache`, `.ruff_cache`, `build`,
`dist`, `*.egg-info`, and `node_modules`.

Use `--no-default-excludes` to scan those paths intentionally. Repeat `--exclude` for
project-specific generated or vendor trees:

```bash
scope-markers --exclude generated --exclude "*.generated.py" src tests
```

An exclusion may match a basename, the path relative to its scan root, or the normalized
full path. Exclusions apply to recursively discovered files and directories. An explicitly
named supported source file remains an explicit input.

Use `--mark-stubs` to include recursively discovered `.pyi` files and mark docstring-only
or ellipsis-only definitions:

```bash
scope-markers --mark-stubs --fix src
```

Opt in Python-compatible files with another extension by repeating `--include`:

```bash
scope-markers --include "*.bzl" --exclude vendor --fix .
```

Included files must parse as Python syntax under the running interpreter. Exclusions and
generated-directory pruning take precedence during recursive discovery.

Recursive discovery skips symlinked files and directories. Explicit file symlinks are
processed without replacing the link itself.

## Command-line reference

### Operation modes

| Option | Behavior |
|---|---|
| `--fix` | Apply the requested changes atomically |
| `--diff` | Print a unified diff without modifying files |
| `--strip` | Remove recognized managed markers instead of regenerating them |
| `--markdown` | Include eligible Python fences in Markdown processing |

`--fix` and `--diff` are mutually exclusive. `--strip` cannot be combined with policy
selection, shape filters, or `--indent-width`; stripping removes every recognized managed
marker in the selected source.

### Policy and configuration

| Option | Behavior |
|---|---|
| `--preset NAME` | Set the base marker-density preset |
| `--select SELECTOR` | Replace the configured selector set |
| `--extend-select SELECTOR` | Add a selector, group, or prefix |
| `--ignore SELECTOR` | Remove a selector, group, or prefix |
| `--list-selectors` | Print selectors, groups, and presets |
| `--config PATH` | Force one configuration file |
| `--isolated` | Ignore discovered configuration |
| `--show-settings PATH` | Print the resolved policy for a path |
| `--explain PATH` | Explain every candidate decision for a path |

The CLI also exposes the global shape filters:

```text
--skip-inline-suites
--min-span-lines N
--min-body-lines N
--min-body-statements N
--min-clauses N
--min-depth N
--max-depth N
```

### Discovery and output

| Option | Behavior |
|---|---|
| `--mark-stubs` | Include `.pyi`; mark docstring-only and ellipsis-only definitions |
| `--indent-width WIDTH` | Normalize logical block indentation before marking |
| `--include PATTERN` | Include another Python-compatible file pattern; repeatable |
| `--exclude PATTERN` | Exclude recursively discovered paths; repeatable |
| `--no-default-excludes` | Disable built-in generated-directory pruning |
| `--fail-fast` | Stop after the first changed file or processing error |
| `--quiet` | Suppress normal status and summary output |
| `--verbose` | Report every processed file, including clean files |
| `--version` | Print the installed version |

`--quiet` and `--verbose` are mutually exclusive.

In `--diff` mode, standard output is reserved for patch bytes. Status and diagnostic
messages go to standard error, so redirecting the patch is safe.

### Exit statuses

| Status | Meaning |
|---:|---|
| `0` | Clean, or all requested fixes completed successfully |
| `1` | Changes are needed in check or diff mode |
| `2` | Discovery, configuration, decoding, tokenization, parsing, diff, or I/O failed |

## Indentation normalization

`--indent-width WIDTH` normalizes tokenizer-recognized logical block indentation before
markers are regenerated. It converts block-indentation tabs to spaces and adjusts attached
block comments, while preserving multiline continuation alignment and blank-line
whitespace.

It is not a replacement for a general formatter. Run Ruff format, Black, or another
ordinary formatter first.

```diff
 if ready:
-    values = (
+  values = (
         first
         + second
     )
 ####
```

The parenthesized assignment is a continuation, not another compound statement.

## Composing with formatters and linters

Scope Markers should be the final tool that rewrites Python layout:

```text
1. Import sorting and automatic fixes
2. Ruff check --fix or another linter's automatic fixes
3. Ruff format, Black, YAPF, or another Python formatter
4. Any formatter that rewrites Python inside Markdown fences
5. scope-markers --fix, including --markdown where applicable
6. Read-only linting, type checking, tests, packaging, and Markdown checks
```

Ruff format, Black, YAPF, and editor formatters treat `####` as an ordinary comment. They
may move surrounding code or normalize whitespace without restoring the marker policy.
Run Scope Markers again whenever another tool rewrites marker-managed Python.

Flake8 can run after marker insertion, but its spacing rules need to account for the
standalone comments. This repository uses a 100-character limit and ignores `E203`,
`E302`, and `E303`.

### Pre-commit

Place rewriting hooks before Scope Markers and read-only hooks after it. Separate hooks
make the Python and Markdown file types explicit:

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: <your-ruff-version>
    hooks:
      - id: ruff-check
        args: [--fix]
      - id: ruff-format

  - repo: local
    hooks:
      - id: scope-markers-python
        name: scope markers — Python
        entry: scope-markers --fix
        language: system
        types: [python]

      - id: scope-markers-markdown
        name: scope markers — Markdown fences
        entry: scope-markers --markdown --fix
        language: system
        types: [markdown]
```

The repository also includes `.pre-commit-hooks.yaml` for a remote Python hook. Pin a
release tag or commit when consuming it from another repository.

## Programmatic API

Import supported functions from `scope_markers.api`, not from the intentionally minimal
package root.

Format in-memory Python source:

```python
from scope_markers.api import format_source

formatted = format_source(source, filename="BUILD.bzl")
```

Format eligible Python fences in Markdown:

```python
from scope_markers.api import format_markdown_source

formatted_markdown = format_markdown_source(markdown_text)
```

File-oriented APIs include `inspect_file`, `process_file`, `strip_markers`, `strip_file`,
and `discover_python_files` for callers that need inspection, discovery, or atomic writes.

## Boundary semantics

A complete-statement marker appears after the entire construct:

- one marker after a complete `if` / `elif` / `else` chain;
- one marker after a loop and its optional `else`;
- one marker after a complete `try`, including handlers, `else`, and `finally`;
- one marker after a complete `match`.

Clause selectors add boundaries within those constructs. Multiple selected candidates that
resolve to the same physical boundary produce one marker. Nested statements close from
the inside out.

```python
def load(value: str) -> str:
    if value:
        with open(value, encoding="utf-8") as stream:
            return stream.read()
        ####
    ####
    return ""
####
```

Under `classic`, `match` cases receive clause markers as well as the outer statement
marker:

```python
match value:
    case 1:
        handle_one()
    ####
    case _:
        handle_other()
    ####
####
```

Documentation-only and ellipsis-only function stubs are skipped by default. Bodies that
contain `pass` or `raise NotImplementedError` are ordinary bodies and remain eligible.

The name *scope markers* describes the visual convention, not Python's exact name-binding
model. `if`, `for`, and `with` are intentionally eligible even though their suites do not
create lexical name scopes. Lambdas, comprehensions, annotation scopes, and other
expression-level scopes have no closing statement line and are not candidates.

## Marker style and stripping

The formatter recognizes exact standalone `##` and `####` comments. A file that already
uses one style keeps it. Files with no managed markers default to `####`. A file containing
both standalone styles fails instead of forcing an ambiguous choice.

`--strip` removes only recognized standalone marker lines:

```diff
 def run() -> None:
     work()
-####
```

Marker-like text inside strings, inline comments, and ordinary comments is preserved.

Normal formatting removes existing managed markers before regenerating the boundaries
selected by the active policy. Changing policy therefore removes stale markers as well as
adding newly selected ones.

## Safety and limitations

For every Python source fragment, Scope Markers:

1. detects the source encoding and tokenizes physical Python lines;
2. identifies exact standalone managed-marker comments;
3. optionally normalizes logical block indentation;
4. removes managed markers and parses the clean source with the running interpreter;
5. computes eligible statement and clause boundaries;
6. applies the resolved policy and reinserts canonical markers;
7. parses the result again and verifies AST equivalence.

The formatter is idempotent and preserves UTF-8 BOMs, PEP 263 source encodings, LF, CRLF,
bare-CR, and locally mixed newline conventions. It handles spaces, tabs, and leading
form-feed characters according to Python's indentation rules.

Regular files are replaced atomically and retain their ordinary permission bits.
Explicitly supplied file symlinks remain symlinks while their targets are updated.
Recursive discovery skips symlinked files and directories.

Atomic replacement creates a new inode on filesystems that expose that concept. Hard-link
identity, extended attributes, and nonstandard filesystem metadata are outside the
preservation contract.

Diff output preserves LF and CRLF records, reports a missing final newline explicitly,
and quotes unusual path names independently of source encoding. Changed files with
bare-CR line endings cannot be represented safely by the unified-diff renderer; use
`--fix` or convert them to LF or CRLF first.

Scope Markers uses the standard-library tokenizer and AST from the interpreter running it.
Run it with the newest Python syntax used by the target repository.

## Focused responsibility

Scope Markers owns canonical marker placement in Python source and eligible Markdown code
fences. It does not replace the surrounding toolchain.

| Concern | Responsible tool |
|---|---|
| Normal Python wrapping, spacing, and quoting | Ruff format or Black |
| Marker selection and canonical placement | Scope Markers |
| Optional logical block indentation | Scope Markers `--indent-width` |
| Python diagnostics and type checking | Ruff, Flake8, Pyright, or similar tools |
| Markdown structure and prose style | rumdl or another Markdown checker |

## Development

```bash
git clone https://github.com/sheepfling/Python-Scope-Markers.git
cd Python-Scope-Markers
uv sync --extra dev
uv run python -m scripts.ci
```

Apply safe cleanup steps before validation:

```bash
uv run python -m scripts.ci --fix
```

Without `uv`:

```bash
python -m pip install -e ".[dev]"
python -m scripts.ci
```

The CI orchestrator runs the regression suite, diff-contract checks, Ruff, Flake8, Black
compatibility checks, strict Pyright, package-build validation, Scope Markers' self-check,
and rumdl. GitHub Actions validates Python 3.11 through 3.14 on Linux and Windows.

Package versions are derived with `setuptools-scm`: a release tag such as `v0.1.0` becomes
package version `0.1.0`, while untagged checkouts receive a PEP 440 development version.

See [CHANGELOG.md](CHANGELOG.md) for release notes.

[ci-badge]: https://github.com/sheepfling/Python-Scope-Markers/actions/workflows/ci.yml/badge.svg
[ci]: https://github.com/sheepfling/Python-Scope-Markers/actions/workflows/ci.yml
[deps-badge]: https://img.shields.io/badge/runtime%20dependencies-none-success
[pyproject]: pyproject.toml
[python-badge]: https://img.shields.io/badge/Python-3.11--3.14-3776AB?logo=python&logoColor=white
[python]: https://www.python.org/

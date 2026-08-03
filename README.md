# Scope Markers

[![CI][ci-badge]][ci]
[![Python 3.11-3.14][python-badge]][python]
[![Runtime dependencies: none][deps-badge]][pyproject]

**Explicit visual endings for Python's indented compound statements.**

Scope Markers is an opinionated, standard-library-only Python formatter. It
inserts standalone `####` comments where complete compound statements end,
making long or deeply nested code easier to scan.

The formatter is deterministic, idempotent, reversible with `--strip`, and
guarded by an AST-equivalence check. Its markers are ordinary Python comments
and have no runtime effect.

This is a project convention, not a claim about universal Python style. Use it
where visible closing boundaries make the code easier for your team to read.

## Example

Before:

```python
def absolute(value: int) -> int:
    if value < 0:
        return -value
    return value
```

After `scope-markers --fix`:

```python
def absolute(value: int) -> int:
    if value < 0:
        return -value
    ####
    return value
####
```

A marker's indentation identifies the statement it closes. Unlike labels such
as `# end if` or `# end function`, `####` copies no identifier or clause name
that can become stale; Scope Markers regenerates placement from parsed source.

## Installation

Scope Markers requires Python 3.11 or newer.

Install the command from the repository with `uv`:

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
`python -m pip install -e .` in a virtual environment. The installed command
and module entry point are equivalent:

```bash
scope-markers --help
python -m scope_markers --help
```

## Quick start

Check files without changing them, then apply or inspect the proposed markers:

```bash
scope-markers .          # Check; do not modify files.
scope-markers --diff .   # Print the proposed patch.
scope-markers --fix .    # Canonicalize markers in place.
```

For example, this source:

```python
class Worker:
    def run(self, ready: bool) -> None:
        if ready:
            work()
```

becomes:

```python
class Worker:
    def run(self, ready: bool) -> None:
        if ready:
            work()
        ####
    ####
####
```

## Focused responsibility

Scope Markers owns one convention: canonical standalone markers at Python
compound-statement boundaries. It is not a general formatter, linter, type
checker, Markdown checker, or plugin framework.

| Concern                                              | Responsible tool                        |
|------------------------------------------------------|-----------------------------------------|
| Normal Python layout, wrapping, spacing, and quoting | Ruff format or Black                    |
| Canonical standalone scope markers                   | Scope Markers                           |
| Optional logical block indentation                   | Scope Markers `--indent-width`          |
| Python diagnostics and type checking                 | Ruff, Flake8, Pyright, or similar tools |
| Markdown style in this repository                    | rumdl                                   |

## Python API

```python
from scope_markers.api import format_source

formatted = format_source(source, filename="BUILD.bzl")
```

The API returns formatted text without modifying files. File-oriented API
functions are also available for callers that need inspection or atomic writes:
`inspect_file`, `process_file`, `strip_markers`, `strip_file`, and
`discover_python_files`.

Markdown fences are opt-in and use the same formatter inside each standalone
`python`, `py`, or `python3` fenced block:

```python
from scope_markers.api import format_markdown_source

formatted = format_markdown_source(markdown_text)
```

## Discovery and common options

With no paths, the current directory is scanned recursively. Common VCS,
virtual-environment, cache, dependency, and build directories are pruned.
Supplying multiple files or directories is supported. A supplied root that is
itself, or is inside, a generated directory such as `build`, `.venv`, or
`node_modules` is skipped. Explicitly naming a `.py` file bypasses directory
pruning and custom excludes. Use `--mark-stubs` to include `.pyi` files.

The default directory exclusions include common VCS, virtual-environment,
cache, build, and dependency directories such as `.git`, `.venv`, `.uv-cache`,
`.cache`, `build`, `dist`, `*.egg-info`, and `node_modules`. Use
`--no-default-excludes` when you intentionally need to scan those directories;
explicit `--exclude` patterns still apply.

The default invocation is check mode: it reports files needing markers and
returns exit status `1` without changing them. These options cover the common
workflow:

```bash
scope-markers --strip --fix src tests   # remove standalone scope markers
scope-markers --markdown --fix README.md # format Python Markdown fences
scope-markers --mark-stubs --fix src     # include .pyi files
scope-markers --indent-width 2 --fix src # normalize block indentation
scope-markers --verbose src tests        # report every file's status
scope-markers --quiet --fix src tests    # suppress status output
scope-markers --fail-fast .              # stop at the first problem
scope-markers --version                  # show the installed version
```

`--quiet` and `--verbose` are mutually exclusive. In `--diff` mode, standard
output is reserved for patch bytes; status and diagnostic messages go to
standard error. This keeps both changed and already-clean runs safe to redirect
to a patch file. `--diff --verbose` additionally reports each file's status on
standard error.

Every command also works as `python -m scope_markers` when the console script
is not on `PATH`.

`--indent-width WIDTH` normalizes logical Python block indentation to that many
spaces before scope markers are regenerated. It converts block-indentation tabs
to spaces and adjusts block comments, but deliberately preserves multiline
continuation alignment and blank-line whitespace. It is not a replacement for
a full code formatter; when using one, run it before scope markers.

For example, this changes block indentation while preserving the continuation
alignment inside the parenthesized expression:

```bash
scope-markers --indent-width 2 --fix src
```

```python
# Before
if ready:
    values = (
        first
        + second
    )

# After --indent-width 2
if ready:
  values = (
        first
        + second
    )
####
```

There is one marker here because the parenthesized assignment is a continuation,
not another compound statement. `####` is the default marker style—visually two
`##` pairs. If the source already uses standalone `##` markers, Scope Markers
preserves that style instead.

To reverse, or unscope, a file, use `--strip`. It removes exact standalone `##`
and `####` marker comments only; comments containing marker-like text and
ordinary source lines remain unchanged. Like normal formatting, it supports
check mode, `--diff`, and `--fix`. `--strip` intentionally cannot be combined
with `--indent-width`, because stripping does not reformat code:

```bash
scope-markers --strip src tests          # report files containing markers
scope-markers --strip --diff src tests   # show removals as a patch
scope-markers --strip --fix src tests    # remove markers in place
```

For example, `--strip --fix` changes only recognized standalone marker lines:

```python
# Before
def run() -> None:
    work()
####

# After
def run() -> None:
    work()
```

Marker-like text inside strings or ordinary comments is preserved.

Diff output preserves LF and CRLF records and includes explicit markers for a
missing final newline. `--diff` rejects changed files with bare-CR line endings
because unified-diff tools cannot apply those physical boundaries. Use `--fix`
or convert such files to LF or CRLF first.

Patch labels are normalized relative to the enclosing Git worktree, or to a
safe shared root outside Git. Unusual names—such as spaces, tabs, newlines,
quotes, and non-UTF-8 path bytes—are quoted separately from the source-file
encoding so Git can consume the patch.

The default check scans every discovered file so CI can report all required
changes. Use `--fail-fast` for a quick local check that stops after the first
changed file or processing error.

Add repeatable glob exclusions for project-specific generated or vendor trees:

```bash
scope-markers --exclude generated --exclude "*.generated.py" src tests
```

Repeat `--exclude` for an additive OR list: a recursively discovered path is
skipped when it matches any supplied pattern. Each pattern is checked against
the basename, the path relative to its scan root, and the normalized full path.

They apply to recursively discovered files and directories; explicit `.py` paths
remain explicit inputs.

Python-compatible files with another extension can be opted in with repeatable
include patterns. This is useful for formats such as Starlark, whose files
often use `.bzl`:

```bash
scope-markers --include "*.bzl" --fix .
```

For example, scan Starlark files while leaving a generated vendor tree out:

```bash
scope-markers --include "*.bzl" --exclude vendor --fix .
```

Included files still need to be parseable by Python's AST, and exclusions and
generated-directory pruning take precedence.

To process Markdown files from the CLI, add `--markdown`:

```bash
scope-markers --markdown README.md docs --fix
scope-markers --markdown --strip --fix README.md docs
```

Only `python`, `py`, and `python3` fenced blocks are processed. Other Markdown
content and non-Python fences remain unchanged. To preserve a Python example
literally, add `no-scope-markers` to its fence info string:

````markdown
```python no-scope-markers
if ready:
    pass
```
````

The equivalent `scope-markers: off` and `scope-markers=ignore` forms are also
accepted. Each processed Python fence must be valid as a standalone Python
source fragment; a fence cannot continue a class or function from another
fence.

Exit statuses are stable:

- `0`: clean, or successfully fixed;
- `1`: changes are needed in check or diff mode;
- `2`: discovery, decoding, tokenization, parsing, or I/O error.

## Composing with formatters and linters

Scope markers must be the last tool that rewrites Python layout. They are
ordinary comments to Ruff, Black, YAPF, autopep8, and editor formatters; those
tools do not know that `####` represents a scope boundary.

### Recommended sequence

Use this order whenever more than one tool processes the same files:

```text
1. Import sorting and autofixes
2. Ruff check --fix or another linter's autofixes
3. Ruff format, Black, or another code formatter
4. scope-markers --fix
5. Read-only checks: Flake8, Pyright, tests, and packaging
```

### Formatter conflicts

Ruff format, Black, YAPF, autopep8, and editor formatters may move code,
normalize blank lines around markers, or rewrite multiline strings without
regenerating the affected markers. Running one after Scope Markers can therefore
make a previously clean file appear changed again.

If a formatter must run after Scope Markers, run `scope-markers --fix` again as
the final rewriting step. For editor format-on-save, configure the ordinary
formatter before the marker command or exclude marker-managed files from the
later formatter.

### Ruff and Black

Run Ruff autofixes and ordinary formatting before Scope Markers:

```bash
python -m ruff check --fix src tests scripts
python -m ruff format src tests scripts
scope-markers --fix src tests scripts
python -m flake8 src tests scripts
python scripts/check_pyright.py
python -m pytest
```

Black and Ruff are intentionally not run as post-marker format checks. This
repository's `scripts/check_black.py` removes standalone markers in a temporary
copy before asking Black to format and check the source.

### Flake8 and read-only tools

Flake8 is safe after marker insertion, but its configuration needs to account
for standalone marker comments. Use the repository's `.flake8` settings as a
starting point: a 100-character limit and ignores for `E203`, `E302`, and
`E303`. `E203` is compatible with Black; `E302` and `E303` otherwise interpret
the marker comments as unexpected function or class spacing.

Pyright, tests, packaging checks, and rumdl are also read-only with respect to
Python marker placement and belong after Scope Markers.

### Pre-commit and editor hooks

Put all rewriting hooks before the marker hook and read-only hooks after it:

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: <your-ruff-version>
    hooks:
      - id: ruff-check
        args: [ --fix ]
      - id: ruff-format
  - repo: local
    hooks:
      - id: scope-markers
        name: scope markers
        entry: scope-markers --fix
        language: system
        types: [ python ]
```

When adopting scope markers in an existing repository, run the ordinary
formatter once, then run `scope-markers --fix`. This establishes a clean
baseline. Keep the same ordering in local commands, editor actions, hooks, and
CI so each environment produces the same result.

### This repository's CI example

The canonical executable sequence is maintained in
[`scripts/ci.py`](scripts/ci.py) and run by
[`.github/workflows/ci.yml`](.github/workflows/ci.yml). Run it locally with:

```bash
python scripts/ci.py
```

Its formatter boundary is explicit: Ruff checks first, the compatibility check
verifies Black on marker-free temporary copies, and `scope-markers` runs before
the final project-specific validation. Use `python scripts/ci.py --fix` for a
local cleanup pass that allows the safe rewriting steps to update files.

## Marker style detection

The formatter recognizes exact standalone `##` and `####` comments. If a file
already contains one of those styles, newly inserted markers use it. Files with
no existing markers default to `####`. If both styles appear as standalone
markers, formatting fails instead of guessing.

## Exact policy

One marker is emitted after each complete Python compound statement:

- `def` and `async def`;
- `class`;
- complete `if` / `elif` / `else` chains;
- complete `for` / `else`, `async for` / `else`, and `while` / `else` statements;
- `with` and `async with`;
- complete `try` / `except`, `except*`, `else`, and `finally` statements;
- complete `match` statements.

Clause boundaries are marked at their own indentation. For example, an `if`
chain receives one marker, while each `case` block receives a clause marker and
the enclosing `match` statement receives its own outer marker.

Nested statements close from the inside out:

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

`match` cases receive their own clause markers in addition to the enclosing
`match` marker:

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

Documentation-only and ellipsis-only function stubs are skipped by default so
that overloads, protocols, and interface stubs remain compact. Use
`--mark-stubs` for the literal every-compound-statement policy; it also enables
recursive discovery of `.pyi` files:

```bash
scope-markers --fix --mark-stubs src tests
```

`pass` bodies and `raise NotImplementedError` bodies are ordinary bodies and are
marked without this option.

## What is not a marker boundary

The name “scope markers” describes the visual convention, not Python's precise
name-binding model. Lambdas, comprehensions, type-parameter annotation scopes,
and other expression-level scopes have no closing statement line where a
standalone marker can be inserted. Conversely, `if`, `for`, and `with` suites do
not create lexical name scopes, but they are intentionally marked because they
are indented compound statements.

## Parser-version rule

The tool uses the standard-library tokenizer and AST from the Python interpreter
running it. It therefore understands all syntax supported by that interpreter,
but an older interpreter cannot parse syntax introduced by a newer Python
release. Run the tool under the newest Python syntax used by the repository.

## Safety properties

The formatter:

- identifies markers as real standalone comment tokens, not matching text inside
  strings or inline comments;
- preserves UTF-8 BOMs and PEP 263 source encodings;
- preserves LF, CRLF, bare-CR, and locally mixed newline conventions;
- handles spaces, tabs, and leading form-feed characters using Python's indentation rules;
- validates that the formatted source has the same AST shape;
- writes regular files atomically and preserves executable permission bits;
- leaves explicitly supplied symlinks intact while updating their target;
- skips symlinked files and directories during recursive discovery;
- is idempotent.

Atomic replacement creates a new inode on filesystems that expose that concept,
so hard-link identity and nonstandard filesystem metadata are outside the
formatter's preservation contract.

## Install as a command

From a cloned checkout, install the command with one of these supported methods:

```bash
git clone https://github.com/sheepfling/Python-Scope-Markers.git
cd Python-Scope-Markers
```

The script can always be copied directly. The project can also be installed as a
small command-line tool:

```bash
uv tool install .
scope-markers --fix src tests
```

The package version is managed by `setuptools-scm`. Release tags such as
`v0.1.0` become package version `0.1.0`; untagged checkouts receive a PEP 440
development version automatically.

or:

```bash
pipx install .
scope-markers --fix src tests
```

These commands require `uv` or `pipx` to be installed and available on `PATH`.
If installation reports a missing command, install the corresponding tool first
or use `python -m pip install -e .` inside a virtual environment.

For a one-off local checkout, use `uvx` or `pipx run` when you want an isolated
temporary invocation without installing a persistent application. Both commands
resolve the package from the current checkout:

```bash
uvx --from . scope-markers --fix src tests
pipx run --spec . scope-markers --fix src tests
```

Use `uv` or an ordinary virtual environment for the complete development tool
set. `pipx` is intended for isolated applications, not for coordinating this
project's pytest, Ruff, Black, Flake8, Pyright, and build dependencies:

```bash
uv sync --extra dev
uv run python scripts/ci.py
```

## Pre-commit

The project includes `.pre-commit-hooks.yaml` for use after publishing the
repository. For an already installed local command, use a system-language hook:

```yaml
repos:
  - repo: local
    hooks:
      - id: scope-markers
        name: scope markers
        entry: scope-markers --fix
        language: system
        types: [ python ]
```

## Development

```bash
python -m pip install -e ".[dev]"
pytest -q
ruff check src scripts tests
flake8 src scripts tests
python scripts/check_pyright.py
python scripts/check_build.py
python -m scope_markers src scripts tests
python scripts/check_rumdl.py
```

For ordinary Python formatting, run Black before applying the project-specific
scope markers:

```bash
black src tests scripts
scope-markers --fix src tests scripts
```

The complete validation roles are:

| Tool                | Command                                     | Purpose                                                                   |
|---------------------|---------------------------------------------|---------------------------------------------------------------------------|
| Ruff                | `ruff check src scripts tests`              | Fast linting, annotation-completeness, and autofix-compatible diagnostics |
| Diff contract       | `python scripts/check_diff.py`              | Verify emitted patches with Git across newline and encoding cases         |
| Black               | `black src tests scripts`                   | Ordinary Python formatting before markers                                 |
| Black compatibility | `python scripts/check_black.py`             | Black format/check smoke test with standalone markers removed             |
| Flake8              | `flake8 src scripts tests`                  | Compatibility lint pass using `.flake8`                                   |
| Pyright             | `python scripts/check_pyright.py`           | Strict type checking for `src`, `scripts`, and `tests`                    |
| Pytest              | `pytest -q`                                 | Regression test suite                                                     |
| Build               | `python scripts/check_build.py`             | Wheel packaging check                                                     |
| Scope markers       | `python -m scope_markers src scripts tests` | Project-specific marker check                                             |
| rumdl               | `python scripts/check_rumdl.py`             | Markdown cleanliness and style checks                                     |

Ruff's annotation rules require parameters and return values to be annotated for
new functions, methods, and test helpers. Pyright then type-checks the package
and CI scripts in strict mode; tests are covered by Ruff and the runtime suite.

Black is intentionally not run as a post-marker `--check`: Black and Ruff both
normalize the whitespace and multiline strings around the required `####`
markers. Flake8 is safe to run after markers because its project configuration
matches the repository's line length and ignores the formatter-incompatible
`E203` rule. It also ignores `E302` and `E303`, which otherwise treat the
required standalone `####` marker comments as function or class boundaries.

The complete local/CI check sequence is also available as one command:

```bash
python scripts/ci.py
```

For a local cleanup pass, add `--fix`. This enables Ruff's safe fixes and
allows `scope-markers` to update the source files, then runs the remaining
checks against the result:

```bash
python scripts/ci.py --fix
```

GitHub Actions runs that sequence on Python 3.11, 3.12, 3.13, and 3.14.

The regression suite covers every compound-statement family, one-line suites,
branch chains, nested same-line endings, generic definitions, marker-like text,
multiline strings, Unicode line separators, tabs, and leading form-feed
characters. It also covers all conventional newline forms, mixed newlines,
BOMs, legacy encodings, executable files, symlinks, recursive discovery,
diffs, exit statuses, syntax diagnostics, and self-idempotence.

[ci-badge]: https://github.com/sheepfling/Python-Scope-Markers/actions/workflows/ci.yml/badge.svg
[ci]: https://github.com/sheepfling/Python-Scope-Markers/actions/workflows/ci.yml
[deps-badge]: https://img.shields.io/badge/runtime%20dependencies-none-success
[pyproject]: pyproject.toml
[python-badge]: https://img.shields.io/badge/Python-3.11--3.14-3776AB?logo=python&logoColor=white
[python]: https://www.python.org/

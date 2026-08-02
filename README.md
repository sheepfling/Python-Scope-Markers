# Scope Markers

A small, standard-library-only Python formatter that inserts standalone `####`
comments at the end of Python compound statements.

The runtime formatter is packaged under `src/scope_markers/`. The surrounding
project files make it testable, installable, and suitable for CI without adding
runtime dependencies.

The package is intentionally layered:

- `scope_markers.__init__` is intentionally kept minimal;
- `scope_markers._implementation` contains formatting, discovery, and file operations;
- `scope_markers.cli` owns command-line parsing and command behavior;
- `scope_markers.__main__` provides `python -m scope_markers`.

New CLI options or commands should be added to `cli.py`; new formatter behavior
belongs in `_implementation.py`. Import implementation APIs from their owning
module rather than relying on package-level re-exports.

## Quick use

Check files without changing them:

```bash
scope-markers src tests scripts
```

Canonicalize files in place:

```bash
scope-markers --fix src tests scripts
```

Show the proposed changes:

```bash
scope-markers --diff src tests scripts
```

With no paths, the current directory is scanned recursively. Common VCS,
virtual-environment, cache, dependency, and build directories are pruned.
Supplying multiple files or directories is supported. A supplied root that is
itself, or is inside, a generated directory such as `build`, `.venv`, or
`node_modules` is skipped. Explicitly naming a `.py` file bypasses directory
pruning and custom excludes.

Add repeatable glob exclusions for project-specific generated or vendor trees:

```bash
scope-markers --exclude generated --exclude "*.generated.py" src tests
```

Exclusion patterns match a path's basename, its path relative to the supplied
root, or its normalized path. They apply to recursively discovered files and
directories; explicit `.py` paths remain explicit inputs.

Exit statuses are stable:

- `0`: clean, or successfully fixed;
- `1`: changes are needed in check or diff mode;
- `2`: discovery, decoding, tokenization, parsing, or I/O error.

## Formatter ordering

Run ordinary formatters first and scope markers last:

```bash
python -m ruff check --fix src tests scripts
python -m ruff format src tests scripts
scope-markers --fix src tests scripts
```

Ruff does not know this project-specific marker convention, so running Ruff after
scope markers may move surrounding code without restoring the markers.

## Using scope markers with downstream tooling

Treat scope-marker insertion as the final formatting stage for any files that
contain markers. A downstream pipeline should use this order:

```text
1. Ruff check --fix, or another linter's autofixes
2. Ruff format or Black
3. scope-markers --fix
4. Flake8, Pyright, tests, and packaging checks
```

Do not run Ruff format or Black after `scope-markers --fix`. Both formatters
interpret `####` as an ordinary comment and may normalize the blank lines around
markers or rewrite multiline string literals. There is no formatter rule that
makes them understand `####` as a scope boundary. If a downstream editor runs
format-on-save, configure it to run before scope-marker insertion or exclude
marker-managed files from that formatter.

Flake8 can run after marker insertion. Match this project's settings if you want
consistent results: use a 100-character line limit and ignore `E203`, while
excluding virtual environments, build outputs, and cache directories. The
repository's `.flake8` file is a ready-to-copy example.

For pre-commit, place the ordinary formatter hooks before the scope-marker hook:

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
      - id: scope-markers
        name: scope markers
        entry: scope-markers --fix
        language: system
        types: [python]
```

If files already contain scope markers, run the ordinary formatter once before
enabling the marker hook. Subsequent changes should flow through the same order
to avoid formatter churn.

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

Clauses are not marked separately. For example, one marker closes an entire
`if` chain, and one marker closes an entire `match` statement rather than each
`case` block.

Documentation-only and ellipsis-only function stubs are skipped by default so
that overloads, protocols, and interface stubs remain compact. Use
`--mark-stubs` for the literal every-compound-statement policy:

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

For a one-off local checkout, the command can also be run without installing a
persistent application:

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
        types: [python]
```

## Development

```bash
python -m pip install -e ".[dev]"
pytest -q
ruff check .
flake8 src scripts tests
pyright
python -m build --wheel
scope-markers .
```

For ordinary Python formatting, run Black before applying the project-specific
scope markers:

```bash
black src tests scripts
scope-markers --fix src tests scripts
```

The complete validation roles are:

| Tool          | Command                    | Purpose                                                                   |
|---------------|----------------------------|---------------------------------------------------------------------------|
| Ruff          | `ruff check .`             | Fast linting, annotation-completeness, and autofix-compatible diagnostics |
| Black         | `black src tests scripts`  | Ordinary Python formatting before markers                                 |
| Flake8        | `flake8 src scripts tests` | Compatibility lint pass using `.flake8`                                   |
| Pyright       | `pyright`                  | Strict type checking for `src` and `scripts`                              |
| Pytest        | `pytest -q`                | Regression test suite                                                     |
| Build         | `python -m build --wheel`  | Wheel packaging check                                                     |
| Scope markers | `scope-markers .`          | Project-specific marker check                                             |

Ruff's annotation rules require parameters and return values to be annotated for
new functions, methods, and test helpers. Pyright then type-checks the package
and CI scripts in strict mode; tests are covered by Ruff and the runtime suite.

Black is intentionally not run as a post-marker `--check`: Black and Ruff both
normalize the whitespace and multiline strings around the required `####`
markers. Flake8 is safe to run after markers because its project configuration
matches the repository's line length and ignores the formatter-incompatible
`E203` rule.

The complete local/CI check sequence is also available as one command:

```bash
python scripts/ci.py
```

GitHub Actions runs that sequence on Python 3.11, 3.12, 3.13, and 3.14.

The regression suite covers every compound-statement family, one-line suites,
branch chains, nested same-line endings, generic definitions, marker-like text,
multiline strings, Unicode line separators, tabs, and leading form-feed
characters. It also covers all conventional newline forms, mixed newlines,
BOMs, legacy encodings, executable files, symlinks, recursive discovery,
diffs, exit statuses, syntax diagnostics, and self-idempotence.

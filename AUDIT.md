# Scope Markers 0.1 Audit

Audit date: 2026-07-31

## Language coverage

The Python language reference defines these compound-statement families:

- `if`;
- `while`;
- `for` and `async for`;
- `try` and `try*`;
- `with` and `async with`;
- `match`;
- function and async-function definitions;
- class definitions.

The formatter maps those families to `ast.If`, `ast.While`, `ast.For`,
`ast.AsyncFor`, `ast.Try`, `ast.TryStar`, `ast.With`, `ast.AsyncWith`,
`ast.Match`, `ast.FunctionDef`, `ast.AsyncFunctionDef`, and `ast.ClassDef`.
No compound-statement family is omitted in the Python 3.11 through 3.14 grammar
reviewed for this release.

Python 3.13 type-parameter defaults do not introduce a new statement family.
Python 3.14 template strings, lazy annotations, and unparenthesized multiple
exception types likewise do not introduce a new compound-statement AST family.
The Python 3.14 exception syntax still maps to `ast.Try` or `ast.TryStar`.

## Clause policy

`elif`, `else`, `except`, `except*`, `finally`, and `case` begin clauses within a
larger compound statement. They are deliberately not emitted as independent
markers. This keeps chains readable and matches the prior repository policy.

## Expression-level scopes

Lambdas, comprehensions, generic type-parameter annotation scopes, and lazily
evaluated annotation scopes can affect name binding, but they are expressions or
implicit compiler scopes rather than indented compound statements. There is no
standalone source boundary at which this formatter should insert `####`.

## Edge cases hardened in 0.1

- bare-CR source files;
- mixed newline files with local newline selection;
- Unicode line separators inside string contents;
- tabs and leading formfeeds in indentation;
- nested compound statements ending on the same physical line;
- one-line suites and semicolon-separated suites;
- decorators and generic function/class definitions;
- Python 3.13 type-parameter defaults;
- Python 3.14 PEP 758 exception syntax in the CI matrix;
- Python 3.14 template strings in the CI matrix;
- marker text inside multiline strings and template strings;
- marker-like comments that are not standalone `####` comments;
- UTF-8 BOMs and non-UTF-8 PEP 263 encodings;
- missing final newlines;
- atomic replacement and executable mode preservation;
- explicit symlink targets versus recursively discovered symlinks;
- nonexistent or non-Python explicit paths;
- tokenizer and parser line/column diagnostics;
- unified diff, quiet, version, and strict stub-policy modes.

## Validation performed

- 56 collected pytest cases on Python 3.13: 52 passed and four expected
  Python 3.14/platform-specific cases skipped as intended.
- Bytecode compilation of the formatter and test module.
- Self-formatting and self-idempotence.
- Wheel build and clean wheel installation with a working `scope-markers`
  console entry point.
- In-memory formatting and second-pass idempotence across 615 Python files from
  the installed Python 3.13 standard library: zero failures.

The repository CI matrix is configured for Python 3.11, 3.12, 3.13, and 3.14 so
version-specific parser behavior is exercised across the supported range.

## Known boundaries

- Syntax newer than the interpreter running the tool cannot be parsed. Run the
  formatter under the newest Python syntax used by the repository.
- `.pyi` files and notebooks are intentionally outside the default file set.
- A standalone `####` comment is considered tool-owned wherever it occurs as a
  comment token; use a non-exact marker when the comment is human-authored text.
- Atomic replacement may break hard-link identity and does not promise to retain
  nonstandard ACLs or extended filesystem metadata.
- The tool does not attempt to honor `.gitignore`; it uses a small deterministic
  built-in directory-pruning list. Explicit `.py` paths are always accepted.

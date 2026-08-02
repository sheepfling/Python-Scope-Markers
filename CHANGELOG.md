# Changelog

## 0.1.0

- Covers every compound-statement family in the Python 3.11–3.14 grammar.
- Adds `--diff`, `--quiet`, `--version`, and `--mark-stubs`.
- Correctly handles bare-CR and locally mixed newline files.
- Uses physical Python line boundaries rather than broad Unicode `splitlines()`.
- Handles tabs and leading form-feed characters using Python indentation expansion.
- Preserves BOMs, declared source encodings, and executable permission bits.
- Uses atomic replacement and preserves explicit symlinks.
- Skips recursively discovered symlink targets and common generated trees.
- Reports missing and non-Python explicit paths instead of silently succeeding.
- Reports tokenizer failures with line and column information.
- Verifies AST-shape preservation and formatter idempotence.
- Initial isolated AST-based checker and fixer extracted from the IMU error-model
  repository.

<!-- managed by sync-workbench — do not edit manually -->

# Python Development Rules

## Naming (Python-specific additions)

Use `snake_case` (underscores) in Python file names to stay consistent with Python conventions. Hyphens are reserved for non-Python contexts (e.g., date components).

```
src/myapp/add_entries.py       # not add-entries.py
tests/test_normalize.py         # not test-normalize.py
```

## Workflow (Python-specific additions)

Refactor step: iterate with `uv run ruff check . --fix` + `uv run ruff format .` + `uv run ty` while staying green.

**Pre-commit enforcement**
- Run `uv run ruff check . --fix` and `uv run ruff format .` and `uv run ty` before committing.
- The PreToolUse guard hook (`guard-python-commit.sh`) automatically blocks `git commit`, `git push`, and `gh pr create` if ruff/ty checks fail.

**External package adoption**
- Version pinned in `pyproject.toml` (not just manifest — explicit version constraint).

## Output & Logging

All output flows through well-defined channels. Keep stdout clean for command results and stderr for diagnostics.

| Channel | What goes here | How |
|---------|----------------|-----|
| **stdout** | Command results, generated data | `print()` (CLI layer only) |
| **stderr** | Status, progress, warnings, errors | `logger.info()`, `logger.warning()`, `logger.error()` |

### Rules

1. **Never use `print()` for status messages** — use `logger.info()` instead. Using `print()` pollutes stdout and corrupts piped output.
2. **Reserve `print()` for CLI output only** — library code must never use `print()`.
3. **Use the `logging` module** — never raw `print()` for diagnostics.
4. **Create per-module loggers:**
   ```python
   import logging
   logger = logging.getLogger(__name__)
   ```
5. **Log levels:**
   - `error` — operation failed, cannot recover (visible by default)
   - `warning` — data issue that degrades results (visible by default)
   - `info` — major operation status (requires `-v`)
   - `debug` — detailed state, intermediate values (requires `-vv`)
6. **Concise debug messages** — consolidate related values into one message.

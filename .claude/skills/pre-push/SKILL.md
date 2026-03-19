---
name: pre-push
description: Run tests and validation before pushing
---

# Pre-push Checks

Run the mandatory pre-push checks and report results.

## Steps

1. Run `uv run ruff check .` to verify lint passes.
2. Run `uv run ty` to verify type checking passes.
3. Run `uv run python -m pytest -q` to execute all tests.
4. Run `uv run blx validate` to verify bibliography data integrity.
5. Report results:
   - If all pass: report success, safe to push.
   - If any fail: show the errors and suggest fixes.

# Feature & Change Workflow

1. Write/extend tests first (happy path, edge case, failure mode).
2. **Verify RED** — run the test and confirm it fails for the expected reason (missing feature, not a typo). A test that passes immediately proves nothing.
3. Minimal implementation to make the test pass — nothing more.
4. **Verify GREEN** — all tests pass, output clean.
5. Refactor while staying green. Iterate (`uv run ruff check . --fix` + `uv run ruff format .` + `uv run ty`).
6. Review diff size and justification.
7. Non-compliance (skipped tests, stale docs) => rejection.

**Bug fixes** — always write a failing test that reproduces the bug *before* fixing it. The test proves the fix and prevents regression.

**Auto-commit for small features**
- After all checks pass (ruff, ty, tests, validation), commit automatically — do not wait for the user to manually prompt "commit".
- Use the `/commit` skill to create the commit.

**Pre-commit checklist (mandatory, every commit)**
- Before every commit, run `uv run ruff check . --fix` and `uv run ruff format .` and `uv run ty`.
- Fix **all** warnings and formatting issues, even if they were not caused by your change.
- Do not commit until all commands pass cleanly with zero errors.

**External package adoption checklist**
- Docs consulted (version-specific)
- Minimal reproduction confirming behavior
- Return/error semantics verified
- Integration test exists
- Version pinned in `pyproject.toml`

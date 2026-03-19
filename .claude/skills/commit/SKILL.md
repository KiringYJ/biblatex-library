---
name: commit
description: Run pre-commit checks, stage relevant files, and create a conventional commit
---

# Commit Skill

Stage relevant changes and create a well-formatted conventional commit.

## Current State

!`git status`

!`git diff --stat`

!`git log --oneline -5`

## Steps

1. Run `uv run ruff check . --fix` to lint the entire codebase.
2. Run `uv run ruff format .` to format the entire codebase.
3. Run `uv run ty` to check for type errors.
   - If any step fails: show errors and fix them before proceeding.
4. Run `uv run python -m pytest -q` to verify tests pass.
5. Review the changes shown above. If you need more detail, run `git diff` for specific files.
6. Stage only relevant files by name — do NOT use `git add -A` or `git add .`.
7. Write a concise conventional commit message (e.g., `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `perf:`, `chore:`).
   - Focus on the "why", not the "what".
   - Keep the first line under 72 characters.
   - Follow the commit style shown above.
8. Create the commit. Do NOT force push. Do NOT amend unless explicitly asked.
9. Run `git status` to confirm the commit succeeded.

## Rules

- Never commit files that contain secrets (.env, credentials, API keys).
- Never use `--no-verify` or skip hooks.
- If push is needed, the user will ask separately.

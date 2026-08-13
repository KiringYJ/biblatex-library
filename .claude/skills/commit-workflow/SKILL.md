---
name: commit-workflow
description: Prepare, verify, stage, and create atomic one-logical-change git commits with Conventional Commit subjects, enabled pre-commit hooks, and optional Lore trailers. Use when a user asks to commit, prepare a commit, write a commit message, push, or open a PR, replacing vendor-specific commit command plugins with a portable project workflow.
---

<!-- agent-workbench: managed portable-skill -->

# Commit Workflow

## Workflow

1. Read `.agents/prompts/commit-workflow.md` if present.
2. Run `git status --short`.
3. Inspect relevant diffs before staging.
4. Confirm the commit contains exactly one logical change; split unrelated edits.
5. Run project verification when practical.
6. Stage only intentional files.
7. Re-check staged diff.
8. Commit with an intent-oriented Conventional Commit subject and enabled pre-commit hooks.
9. Add Lore trailers for non-trivial decisions when useful.
10. Push or open a PR only if explicitly requested.

## Safety

Never stage unrelated files, bypass hooks, push, rewrite history, or run destructive git commands without explicit authorization. Treat pre-commit hook failures as issues to diagnose and fix, not as obstacles to skip.

---

# Claude Adapter

Generate a project skill at `.claude/skills/commit-workflow/SKILL.md` when the Claude target is enabled. Keep the generated skill body derived from the canonical neutral skill and add only this adapter note.

If Claude Code has an official, bundled, or installed equivalent for this capability in the current environment, prefer that native surface and keep the canonical skill as fallback. Do not require Claude Marketplace or user-scope plugin installation.

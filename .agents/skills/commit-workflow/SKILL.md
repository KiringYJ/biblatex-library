---
name: commit-workflow
description: Prepare, verify, stage, and create focused git commits with Conventional Commit subjects and optional Lore trailers. Use when a user asks to commit, prepare a commit, write a commit message, push, or open a PR, replacing vendor-specific commit command plugins with a portable project workflow.
---

<!-- agent-workbench: managed portable-skill -->

# Commit Workflow

## Workflow

1. Read `.agents/prompts/commit-workflow.md` if present.
2. Run `git status --short`.
3. Inspect relevant diffs before staging.
4. Run project verification when practical.
5. Stage only intentional files.
6. Re-check staged diff.
7. Commit with an intent-oriented Conventional Commit subject.
8. Add Lore trailers for non-trivial decisions when useful.
9. Push or open a PR only if explicitly requested.

## Safety

Never stage unrelated files, bypass hooks, push, rewrite history, or run destructive git commands without explicit authorization.

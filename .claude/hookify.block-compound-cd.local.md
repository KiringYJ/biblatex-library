---
name: block-compound-cd
enabled: true
event: bash
pattern: ^\s*cd\s+[^\s;]+\s*(&&|;)
action: block
---

**BLOCKED: Compound `cd` command detected.**

Do not use `cd <path> && command`. The working directory persists between Bash calls.

**Correct approach:**
1. Run `cd <path>` once as a standalone call at the start of the session
2. Use bare commands in all subsequent calls (e.g., `uv run pytest`, `git status`)

Compound forms like `cd /foo && uv run pytest` violate the project rule in `.claude/rules/interaction.md`.

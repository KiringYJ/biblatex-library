---
name: skill-authoring
description: Create or update portable Agent Skills under .agents/skills with concise SKILL.md instructions and optional scripts, references, or assets. Use when a user wants skill-creator behavior that works across Codex, Gemini, Claude Code, OpenCode, or other agents without relying on one vendor's built-in creator.
---

<!-- agent-workbench: managed portable-skill -->

# Skill Authoring

## Workflow

1. Read `.agents/prompts/create-agent-skill.md` if present.
2. Gather concrete trigger examples and the repeated task the skill should improve.
3. Create `.agents/skills/<skill-name>/SKILL.md`.
4. Use frontmatter with only `name` and `description` unless a target explicitly requires more.
5. Add `scripts/`, `references/`, or `assets/` only when they materially reduce repeated work or increase reliability.
6. Test scripts and validate frontmatter.

## Quality Bar

Keep skills concise, non-obvious, reusable, project-safe, and actionable.

---
name: guardrail-authoring
description: Create or update vendor-neutral project guardrails under .agents/guardrails and optionally generate thin Claude, Codex, or Gemini hook/config adapters. Use when a user wants hookify-like behavior, safety rules, tool-use constraints, or repeatable enforcement without making a vendor-specific hook format the source of truth.
---

<!-- agent-workbench: managed portable-skill -->

# Guardrail Authoring

## Workflow

1. Read `.agents/prompts/create-guardrail.md` if present.
2. Capture the rule intent, trigger pattern, decision, and remediation message.
3. Write the canonical rule to `.agents/guardrails/<slug>.md`.
4. Generate vendor-specific hook/config adapters only when explicitly requested.
5. Validate any generated JSON, TOML, shell, PowerShell, Python, or JavaScript.

## Guardrails

- Prefer guidance when enforcement is not deterministic.
- Keep executable hooks project-local.
- Do not install global hooks or marketplace plugins.

---

# Claude Adapter

Generate a project skill at `.claude/skills/guardrail-authoring/SKILL.md` when the Claude target is enabled. Keep the generated skill body derived from the canonical neutral skill and add only this adapter note.

If Claude Code has an official, bundled, or installed equivalent for this capability in the current environment, prefer that native surface and keep the canonical skill as fallback. Do not require Claude Marketplace or user-scope plugin installation.

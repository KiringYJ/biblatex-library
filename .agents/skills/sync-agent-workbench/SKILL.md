---
name: sync-agent-workbench
description: Synchronize, audit, or repair vendor-neutral agent-workbench files in a project. Use when a user wants every project to carry canonical AI_AGENT_GUIDE.md, thin Claude/Codex/Gemini/OpenCode entrypoints, portable prompts, and portable Agent Skills without depending on a vendor marketplace, plugin, global config, or submodule.
---

<!-- agent-workbench: managed portable-skill -->

# Sync Agent Workbench

## Workflow

1. Read `AI_AGENT_GUIDE.md` and `AI_AGENT_PROJECT.md` if present.
2. Choose the requested workflow:
   - Sync: follow `.agents/prompts/sync-agent-workbench.md` when present, otherwise use the upstream `prompts/sync-agent-workbench.md`.
   - Audit: follow `.agents/prompts/audit-agent-workbench.md` when present.
   - Repair: follow `.agents/prompts/repair-agent-workbench.md` when present.
3. Modify only the files allowed by the selected prompt.
4. Keep `AI_AGENT_PROJECT.md` manual after initial creation.
5. Keep vendor entrypoints thin and canonical content under `AI_AGENT_GUIDE.md`, `.agents/prompts/`, and `.agents/skills/`.
6. Verify with `git status --short`, `git diff --stat`, and manifest path checks when working in the workbench repository.

## Guardrails

- Do not install marketplace plugins, extensions, global/user-scope settings, or git submodules.
- Do not modify application source code during sync unless the user separately requested application changes.
- Do not create `AGENT.md`; use `AGENTS.md`.

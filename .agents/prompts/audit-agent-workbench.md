<!-- agent-workbench: managed portable-prompt -->

# Audit Agent Workbench Prompt

Audit a consumer repository for consistency with the vendor-neutral `agent-workbench` model. This prompt is read-only unless the user explicitly asks for repairs.

## Read-only rule

Do not modify files in audit mode. Inspect and report only.

## Checks

1. `AI_AGENT_GUIDE.md`
   - Exists.
   - Contains the managed metadata marker with `agent-workbench: managed`.
   - References the selected profile and source.
   - Does not contain obvious unmarked project-specific content that should live in `AI_AGENT_PROJECT.md`.

2. `AI_AGENT_PROJECT.md`
   - Exists, or the repository clearly documents that it is intentionally absent.
   - Contains project-specific sections for architecture, build commands, test commands, important files, domain terms, and constraints when possible.

3. `CLAUDE.md`
   - Is a thin entrypoint.
   - References `@AI_AGENT_GUIDE.md` and `@AI_AGENT_PROJECT.md`.
   - Does not contain a large duplicated copy of the shared guide.

4. `AGENTS.md`
   - Is a thin Codex/OpenCode/general entrypoint.
   - Tells agents to read `AI_AGENT_GUIDE.md` and `AI_AGENT_PROJECT.md`.
   - Does not rely on `@` imports.
   - Does not contain a large duplicated copy of the shared guide.

5. `GEMINI.md`
   - Is a thin entrypoint.
   - References `@AI_AGENT_GUIDE.md` and `@AI_AGENT_PROJECT.md`.
   - Does not contain a large duplicated copy of the shared guide.

6. `opencode.json`
   - Is valid JSON.
   - Includes `AI_AGENT_GUIDE.md` and `AI_AGENT_PROJECT.md` in `instructions`.
   - Preserves unrelated settings.

7. `.codex/config.toml`
   - Exists when Codex config is enabled in `.agent-workbench.yaml`.
   - Is project-scoped.
   - Does not depend on user-scope or machine-local paths.

8. `.agent-workbench.yaml`
   - Exists.
   - Has valid `source`, `profile`, `modules`, `targets`, and `preserve` sections.
   - Names modules that exist in the workbench manifest.

9. Portable workflows
   - `manifest.yaml` registers capabilities and each capability file exists.
   - Each capability declares a canonical skill or prompt, portability level, and vendor targets.
   - `.agents/prompts/` contains the registered portable prompts from the workbench manifest.
   - `.agents/skills/` contains the registered portable skills from the workbench manifest.
   - Canonical workflow content lives under `.agents/`, not only in Claude/Codex/Gemini-specific folders.
   - If the Claude target is enabled, generated `.claude/skills/*/SKILL.md` files are thin surfaces derived from canonical capabilities.
   - No registered portable prompt or skill is a symlink.

10. Vendor neutrality
   - No Claude marketplace/plugin dependency is required for guide loading.
   - No git submodule is required.
   - No global or user-scope configuration is required.
   - No `AGENT.md` typo exists as the primary entrypoint.

## Output

Return a structured report:

- Overall status: `PASS`, `WARN`, or `FAIL`.
- Findings grouped by severity.
- Exact files and lines when practical.
- Suggested repair action for each issue.
- Confirmation that no files were modified.

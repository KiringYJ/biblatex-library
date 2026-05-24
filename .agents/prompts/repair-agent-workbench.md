<!-- agent-workbench: managed portable-prompt -->

# Repair Agent Workbench Prompt

Repair missing or malformed agent-workbench instruction files in a consumer repository while preserving project-specific manual content.

## Allowed repairs

You may create or repair only:

- `AI_AGENT_GUIDE.md`
- `AI_AGENT_PROJECT.md` if missing
- `CLAUDE.md`
- `AGENTS.md`
- `GEMINI.md`
- `opencode.json`
- `.codex/config.toml`
- `.agent-workbench.yaml`
- `.agents/prompts/<registered-prompt>.md`
- `.agents/skills/<registered-skill>/SKILL.md`
- Registered skill resources under `.agents/skills/<registered-skill>/scripts/`, `references/`, and `assets/` when present in the workbench source
- `.claude/skills/<registered-skill>/SKILL.md` when the Claude target is enabled and the capability target requests a Claude generated skill surface

Do not modify application source code. Do not install dependencies, plugins, marketplaces, submodules, global configuration, or user-scope settings.

## Repair process

1. Inspect the repository and current instruction files.
2. Read `.agent-workbench.yaml`; if missing or unusable, recreate it from `templates/agent-workbench.yaml.tpl` using `profile: base` unless the user requested another profile.
3. Resolve profile and modules using `manifest.yaml` and `profiles/*.yaml`.
4. Recreate `AI_AGENT_GUIDE.md` from selected modules.
5. Preserve every existing `AI_AGENT_GUIDE.md` manual block exactly:
   - `<!-- agent-workbench:manual-begin -->`
   - `<!-- agent-workbench:manual-end -->`
6. Create `AI_AGENT_PROJECT.md` only if missing. If it exists, do not rewrite it.
7. Recreate thin `CLAUDE.md`, `AGENTS.md`, and `GEMINI.md` from templates if missing or bloated.
8. Merge `opencode.json` conservatively:
   - Preserve unrelated settings.
   - Add `AI_AGENT_GUIDE.md` and `AI_AGENT_PROJECT.md` to `instructions`.
   - Add `$schema` only if absent.
9. Merge `.codex/config.toml` conservatively:
   - Preserve unrelated settings and comments when practical.
   - Add `project_doc_max_bytes = 65536` only if absent.
10. Repair portable workflows:
   - Read registered capability metadata from `capabilities/*/capability.yaml`.
   - Copy registered `portable_prompts` into `.agents/prompts/`.
   - Copy registered `portable_skills` into `.agents/skills/`.
   - Generate `.claude/skills/<name>/SKILL.md` from canonical skills plus thin Claude adapters when the Claude target is enabled.
   - Preserve unregistered local prompts and skills.
   - Prefer real copied files over symlinks.
   - Do not create other vendor-specific mirrors unless the user explicitly requests them.

## Malformed config handling

If JSON or TOML is malformed:

- Report the parse error.
- In repair mode, preserve the original content in a clearly named local backup next to the file, such as `opencode.json.agent-workbench-backup`.
- Write the minimal valid repaired config.
- Do not discard unrelated settings unless they cannot be parsed; mention that limitation in the final report.

## Final report

Summarize:

- Files repaired or created.
- Files intentionally left untouched.
- Manual content preserved.
- Portable prompts and skills repaired.
- Backups created.
- Any assumptions or unresolved issues.
- Confirmation that no application source code or global configuration was changed.

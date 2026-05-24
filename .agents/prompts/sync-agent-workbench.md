<!-- agent-workbench: managed portable-prompt -->

# Sync Agent Workbench Prompt

Use this prompt to synchronize a consumer repository with the vendor-neutral `agent-workbench` model. This is an LLM-executed workflow; it does not require a custom CLI, marketplace, plugin, submodule, global configuration, or machine-local path.

## Supported natural-language modes

Interpret the user's request and select one mode:

- **full sync**: update managed guide, thin entrypoints, OpenCode config, Codex config, portable prompts, portable skills, and create missing project/config files.
- **guide-only sync**: update only `AI_AGENT_GUIDE.md` and create `.agent-workbench.yaml` if missing.
- **entrypoints-only sync**: update only `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, `opencode.json`, and `.codex/config.toml`.
- **portable-workflows sync**: update only managed `.agents/prompts/` and `.agents/skills/` artifacts.
- **audit-only mode**: inspect and report; do not modify files.
- **repair missing files**: create or repair missing/malformed instruction/config files while preserving manual content.

If the user does not specify a mode, use **full sync**. If the user specifies a profile (for example `rust`, `python`, or `typescript`), set that profile in `.agent-workbench.yaml` and include its modules.

## Hard safety rules

- Do not modify application source code.
- Do not install dependencies.
- Do not install Claude plugins, Claude marketplace entries, global Codex settings, global Gemini settings, or user-scope configuration.
- Do not create git submodules.
- Do not rely on machine-local absolute paths.
- Do not create `AGENT.md`; the correct file is `AGENTS.md`.
- Only update these files unless the user explicitly authorizes more:
  - `AI_AGENT_GUIDE.md`
  - `AI_AGENT_PROJECT.md` only when missing
  - `CLAUDE.md`
  - `AGENTS.md`
  - `GEMINI.md`
  - `opencode.json`
  - `.codex/config.toml`
  - `.agent-workbench.yaml`
  - `.agents/prompts/<registered-prompt>.md`
  - `.agents/skills/<registered-skill>/SKILL.md`
  - `.agents/skills/<registered-skill>/scripts/**`, `.agents/skills/<registered-skill>/references/**`, and `.agents/skills/<registered-skill>/assets/**` when present in the workbench source
  - `.claude/skills/<registered-skill>/SKILL.md` when the Claude target is enabled and the capability target requests a Claude generated skill surface

## Inputs to read

1. Inspect the consumer repository root.
2. Read `.agent-workbench.yaml` if present.
3. Read existing managed files if present, especially `AI_AGENT_GUIDE.md`, to preserve manual blocks.
4. Read the workbench source files from the current checkout or from `KiringYJ/agent-workbench` if the user references the repository remotely:
   - `manifest.yaml`
   - selected `profiles/*.yaml`
   - selected `guide/**/*.md`
   - `templates/*.tpl`
   - registered `portable_prompts` and `portable_skills` from `manifest.yaml`
   - registered `capabilities/*/capability.yaml` and `capabilities/*/vendors/*.md`

## Profile and module resolution

1. If `.agent-workbench.yaml` is missing, create it from `templates/agent-workbench.yaml.tpl` with `profile: base`, unless the user requested another profile.
2. Load `manifest.yaml`.
3. Resolve the selected profile from `profiles/<profile>.yaml`.
4. If a profile has `extends`, load the parent profile first.
5. Concatenate modules in this order:
   - parent profile modules
   - child profile modules
   - explicit `modules:` listed in `.agent-workbench.yaml` that are not already included
6. Validate each module name exists in `manifest.yaml`.
7. If a requested module is missing, report it and continue only if enough modules remain to produce a useful guide.

## AI_AGENT_GUIDE.md generation

Generate `AI_AGENT_GUIDE.md` from `templates/AI_AGENT_GUIDE.md.tpl`.

The top metadata marker must be:

```html
<!--
agent-workbench: managed
source: <repo-or-url>
profile: <profile-name>
updated: <date-or-version>
manual-edits: preserve-marked-sections-only
-->
```

Rules:

- Compose the body from the selected guide modules.
- Preserve existing content inside every manual block exactly:
  - `<!-- agent-workbench:manual-begin -->`
  - `<!-- agent-workbench:manual-end -->`
- Put preserved manual blocks near the top under a `## Preserved Manual Notes` heading, or leave them where the template indicates manual blocks.
- Do not preserve unmarked manual edits in `AI_AGENT_GUIDE.md`; tell the user that only marked blocks are retained.
- The result must be idempotent: running sync again with the same inputs should produce the same file except for an intentional date/version value.

## AI_AGENT_PROJECT.md

- If `AI_AGENT_PROJECT.md` is missing, create it from `templates/AI_AGENT_PROJECT.md.tpl`.
- If it already exists, never overwrite or rewrite it.
- This file is the correct place for architecture, build commands, test commands, important paths, domain terms, and project-specific constraints.

## Thin entrypoints

Create or update these files from templates:

- `CLAUDE.md`: thin Claude Code entrypoint using `@AI_AGENT_GUIDE.md` and `@AI_AGENT_PROJECT.md`.
- `AGENTS.md`: thin Codex/OpenCode/general entrypoint. Do not use `@` imports here.
- `GEMINI.md`: thin Gemini entrypoint using `@AI_AGENT_GUIDE.md` and `@AI_AGENT_PROJECT.md`.

Vendor-specific files must not contain a large duplicated copy of the guide.

## OpenCode config merge

Ensure `opencode.json` includes:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "instructions": [
    "AI_AGENT_GUIDE.md",
    "AI_AGENT_PROJECT.md"
  ]
}
```

If `opencode.json` exists:

- Parse it as JSON.
- Preserve unrelated settings.
- Preserve existing instruction entries.
- Add `AI_AGENT_GUIDE.md` and `AI_AGENT_PROJECT.md` if missing.
- Add `$schema` only if absent.
- Keep output formatted with two-space indentation.

If it is malformed, do not discard it silently. Report the parse error and either repair only with user permission or write a clear backup if the user requested repair mode.

## Codex config merge

Ensure `.codex/config.toml` exists with:

```toml
#:schema https://developers.openai.com/codex/config-schema.json

project_doc_max_bytes = 65536
```

If `.codex/config.toml` exists:

- Preserve unrelated settings and comments when practical.
- Add `project_doc_max_bytes = 65536` only if no `project_doc_max_bytes` setting exists.
- Do not overwrite project-specific model, approval, sandbox, tool, or path settings.

## Portable prompts and skills

For full sync and portable-workflows sync, copy the registered workflow artifacts from the workbench manifest into project-local vendor-neutral paths:

- `portable_prompts.<name>.path` -> `.agents/prompts/<name>.md`
- `portable_skills.<name>.path` -> `.agents/skills/<name>/SKILL.md`
- `capabilities.<name>.path` records the canonical skill, canonical prompts, vendor adapters, official-preferred behavior, and optional generated vendor outputs.

Rules:

- Create `.agents/prompts/` and `.agents/skills/` when missing.
- Copy the managed prompt/skill content from the workbench source.
- If a registered skill folder contains `scripts/`, `references/`, or `assets/`, copy those resources into `.agents/skills/<name>/`.
- Do not delete unregistered local prompts or skills.
- Do not overwrite files under `.agents/skills/<name>/` that are not part of the registered managed source skill.
- Prefer real copied directories over symlinks for portability.
- Do not create vendor-specific mirrors such as `.codex/skills/`, `.gemini/skills/`, or `.opencode/skills/` unless the user explicitly requests them.
- When `targets.claude: true`, generate `.claude/skills/<name>/SKILL.md` for capabilities whose Claude target mode starts with `generated-skill` or is `official-preferred` with fallback enabled. Build it from the canonical neutral `SKILL.md` plus the small `capabilities/<name>/vendors/claude.md` adapter note. Do not install Claude plugins or marketplace entries.
- For Codex, Gemini, and OpenCode, prefer `.agents/skills/<name>/SKILL.md` as the shared generated surface unless the user explicitly requests a vendor-native mirror.
- If a capability is marked `official-preferred` for the active vendor, mention the native implementation as the preferred invocation when available, but still keep the neutral fallback skill available.
- Treat `agent-workbench: managed portable-prompt` and `agent-workbench: managed portable-skill` as overwrite markers.
- If a consumer project already has a local `.agents/prompts/<name>.md` or `.agents/skills/<name>/SKILL.md` with unmarked manual edits, replace it only when the file carries an agent-workbench managed marker or when the user requested repair/full overwrite. Otherwise report the conflict.

## Final report

End with a concise diff-style summary:

- Mode and profile used.
- Files created.
- Files updated.
- Files intentionally left unchanged, especially `AI_AGENT_PROJECT.md`.
- Manual blocks preserved.
- Portable prompts and skills synced or skipped.
- Any parse errors, skipped modules, or assumptions.
- Confirmation that no application source code, dependencies, global config, marketplace, plugin installation, or submodule was modified.

<!-- agent-workbench: managed portable-prompt -->

# Sync Agent Workbench Prompt

Use this prompt to synchronize a consumer repository with the vendor-neutral `agent-workbench` model. This is an LLM-executed workflow; it does not require a custom CLI, marketplace, plugin, submodule, global configuration, or machine-local path.

## Supported natural-language modes

Interpret the user's request and select one mode:

- **full sync**: update managed guide, thin entrypoints, OpenCode config, Codex config, portable prompts, portable skills, create missing project/config files, and update the `.agent-workbench.lock.json` provenance ledger for the scopes actually reconciled.
- **guide-only sync**: update only `AI_AGENT_GUIDE.md` and create `.agent-workbench.yaml` if missing.
- **entrypoints-only sync**: update only `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, `opencode.json`, and `.codex/config.toml`.
- **portable-workflows sync**: update only managed `.agents/prompts/` and `.agents/skills/` artifacts.
- **audit-only mode**: inspect and report; do not modify files.
- **repair missing files**: create or repair missing/malformed instruction/config files while preserving manual content.

If the user does not specify a mode, use **full sync**. If the user asks to install agent-workbench, treat install as the first sync: run the same workflow, create missing config/artifacts, and write the first provenance ledger. If the user specifies a profile (for example `rust`, `python`, or `typescript`), set that profile in `.agent-workbench.yaml` and include its modules.

## Hard safety rules

- Do not modify application source code.
- Do not install dependencies.
- Do not install Claude plugins, Claude marketplace entries, global Codex settings, global Gemini settings, or user-scope configuration.
- Do not create git submodules.
- Do not rely on machine-local absolute paths.
- Do not create `AGENT.md`; the correct file is `AGENTS.md`.
- Do not merge, rebase, or cherry-pick `workspace-config` wholesale into `main`, `dev`, or product feature branches.
- Do not stage or commit workspace-only agent/editor configuration on product branches unless the project explicitly documents that path as project-wide policy.
- Only update these files unless the user explicitly authorizes more:
  - `AI_AGENT_GUIDE.md`
  - `AI_AGENT_PROJECT.md` only when missing
  - `CLAUDE.md`
  - `AGENTS.md`
  - `GEMINI.md`
  - `opencode.json`
  - `.codex/config.toml`
  - `.agent-workbench.yaml`
  - `.agent-workbench.lock.json`
  - `.agents/prompts/<registered-prompt>.md`
  - `.agents/skills/<registered-skill>/SKILL.md`
  - `.agents/skills/<registered-skill>/scripts/**`, `.agents/skills/<registered-skill>/references/**`, and `.agents/skills/<registered-skill>/assets/**` when present in the workbench source
  - `.claude/skills/<registered-skill>/SKILL.md` when the Claude target is enabled and the capability target requests a Claude generated skill surface
  - local `.git/info/exclude` entries for the workspace-overlay paths listed in this prompt, when the repository uses Git

## Workspace-config orphan branch policy

Agent-workbench managed files are workspace overlay by default. In Git repositories, store them on a dedicated orphan branch named `workspace-config` and keep product branches clean unless `AI_AGENT_PROJECT.md` explicitly documents a project-wide exception.

Required invariant:

```text
workspace-config must never be merged, rebased, or cherry-picked wholesale into main, dev, or product feature branches.
```

Before writing files in a consumer Git repository:

1. Detect the current branch and existing tracked files with `git status --short`, `git branch --show-current`, and `git ls-files -- <workspace-paths>`.
2. Treat `main`, `dev`, and `feature/*` as product branches unless the project documents different branch names.
3. Ensure product worktrees locally exclude workspace-overlay paths through `.git/info/exclude`, not project `.gitignore`.
4. If workspace-overlay files are already tracked on a product branch, do not silently remove them from the index. Report the migration command (`git rm --cached ...`) unless the user explicitly requested migration/repair.
5. Generate or refresh the workspace files in the working tree, but do not stage them to a product branch.
6. To version workspace changes, create or update `workspace-config` through a temporary worktree. Push only when the user explicitly requested remote publication or already asked for publish/push.

Default agent-workbench workspace-overlay paths:

```text
AI_AGENT_GUIDE.md
AI_AGENT_PROJECT.md
AGENTS.md
CLAUDE.md
GEMINI.md
.agent-workbench.yaml
.agent-workbench.lock.json
.agents/
.codex/
.claude/
opencode.json
```

Optional local workspace paths such as `.agent/`, `.cursor/`, `.vscode/`, `prompts/`, or `scripts/` may also use the branch, but only after confirming they are not product-owned. If a path is intentionally shared with all contributors, document that exception in `AI_AGENT_PROJECT.md` and treat it as project policy rather than workspace overlay.

## Inputs to read

1. Inspect the consumer repository root.
2. Read `.agent-workbench.yaml` if present. Treat it as human-owned desired configuration only.
3. Read `.agent-workbench.lock.json` if present. Treat it as an agent-owned provenance/baseline ledger, not as user configuration or a package-manager lock.
4. Read existing managed files if present, especially `AI_AGENT_GUIDE.md`, to preserve manual blocks.
5. If the repository uses Git, inspect the current branch, whether `workspace-config` exists, local `.git/info/exclude`, and whether workspace-overlay paths are tracked on the current branch.
6. Read the workbench source files from the current checkout or from `KiringYJ/agent-workbench` if the user references the repository remotely:
   - `manifest.yaml`
   - selected `profiles/*.yaml`
   - selected `guide/**/*.md`
   - `templates/*.tpl`
   - registered `portable_prompts` and `portable_skills` from `manifest.yaml`
   - registered `capabilities/*/capability.yaml` and `capabilities/*/vendors/*.md`

## Provenance ledger and removal detection

`.agent-workbench.yaml` is the human-owned desired configuration. Do not store generated sync state there.

`.agent-workbench.lock.json` is an agent-owned provenance/baseline ledger. It records what the last successful sync actually installed for each scope so later syncs can detect removed, deselected, locally edited, or migrated artifacts. It is a workspace-overlay file and should be versioned/restored with `workspace-config` when the project uses that branch model.

Minimum lockfile shape:

```json
{
  "schemaVersion": 1,
  "generatedAt": "<iso-8601>",
  "source": {
    "repo": "KiringYJ/agent-workbench",
    "branch": "main",
    "requestedRef": "main",
    "resolvedCommit": "<upstream-sha>"
  },
  "manifestDigest": "sha256:<digest>",
  "profile": "base",
  "syncMode": "full|guide-only|entrypoints-only|portable-workflows|repair",
  "targets": { "guide": true, "portable_prompts": true, "portable_skills": true },
  "scopes": {
    "guide": { "resolvedCommit": "<sha>", "manifestDigest": "sha256:<digest>", "lastReconciledAt": "<iso-8601>" },
    "entrypoints": { "resolvedCommit": "<sha>", "manifestDigest": "sha256:<digest>", "lastReconciledAt": "<iso-8601>" },
    "portable_prompts": { "resolvedCommit": "<sha>", "manifestDigest": "sha256:<digest>", "lastReconciledAt": "<iso-8601>" },
    "portable_skills": { "resolvedCommit": "<sha>", "manifestDigest": "sha256:<digest>", "lastReconciledAt": "<iso-8601>" },
    "vendor_adapters": { "resolvedCommit": "<sha>", "manifestDigest": "sha256:<digest>", "lastReconciledAt": "<iso-8601>" }
  },
  "installedArtifacts": [
    {
      "id": "portable_skill:sync-agent-workbench",
      "kind": "portable_skill",
      "scope": "portable_skills",
      "name": "sync-agent-workbench",
      "sourcePath": "skills/sync-agent-workbench/SKILL.md",
      "outputPath": ".agents/skills/sync-agent-workbench/SKILL.md",
      "sourceChecksum": "sha256:<source>",
      "lastAppliedOutputChecksum": "sha256:<output>",
      "resourceManifest": [],
      "markerVersion": "agent-workbench: managed portable-skill",
      "capability": "sync-agent-workbench",
      "vendor": "neutral",
      "profile": "base",
      "managed": true
    }
  ],
  "retainedRemovals": []
}
```

Artifact records should include all generated files in a skill folder (`scripts/`, `references/`, `assets/`) through `resourceManifest`. `manifestDigest` should cover the resolved manifest plus selected profile/capability metadata enough to explain why the desired artifact set changed.

### Active scopes and baseline advancement

Advance only the scopes actually reconciled by the selected mode:

- full sync: all selected scopes.
- guide-only sync: `guide` only.
- entrypoints-only sync: `entrypoints` and vendor config only.
- portable-workflows sync: `portable_prompts`, `portable_skills`, and generated vendor adapters only.
- repair missing files: only repaired scopes and artifacts.

Do not classify or delete artifacts from inactive scopes. Do not advance inactive scope baselines.

### Generated artifact deletion scope

Deletion candidates must normalize to repository-relative paths and stay inside the allowed workspace-overlay outputs:

- `AI_AGENT_GUIDE.md`
- `CLAUDE.md`
- `AGENTS.md`
- `GEMINI.md`
- `opencode.json`
- `.codex/config.toml`
- `.agents/prompts/<registered-prompt>.md`
- `.agents/skills/<registered-skill>/**`
- `.claude/skills/<registered-skill>/**` when generated by the Claude target
- explicitly requested and lockfile-recorded vendor mirrors such as `.codex/skills/**`, `.gemini/skills/**`, or `.opencode/skills/**`

Never delete absolute paths, paths outside the repository root, paths containing `..` traversal, malformed paths, application source files, or local/unmanaged artifacts. `.agent-workbench.lock.json` may be repaired or recreated, but normal upstream-removal cleanup should not delete the ledger itself.

### Removal and drift classification

Use lockfile records plus the current resolved desired set as primary evidence. Use upstream Git history/diff as supporting explanation, not as the only basis for deletion. Use objective ownership signals: lockfile record, managed marker, checksum match against known source/output, tombstone/migration metadata, or explicit user confirmation.

Classify every candidate with one of these exact statuses:

1. **confirmed upstream removal** — lockfile recorded a managed artifact, source identity still matches, current desired set omits it, and local checksum matches the last applied output or the local output is already gone.
2. **confirmed removal with local edits** — same as confirmed upstream removal, but local checksum or resource manifest differs from the lockfile. Default to keep/backup; do not include it in a broad safe delete-all choice unless explicitly selected.
3. **suspected legacy removal** — no usable lockfile exists, but an objective managed ownership signal exists and the artifact is absent from the current upstream manifest. Say this is inferred, not confirmed by Git history.
4. **deselected by local config** — the artifact exists or is lockfile-recorded, but the current profile/targets/sync mode no longer selects it. Do not call this an upstream removal.
5. **source changed / migration required** — source repo, branch, manifest digest, artifact id, source path, or capability identity changed enough that comparison is unsafe. Stop removal classification for affected artifacts and ask for a migration/audit decision.
6. **local unmanaged** — no lockfile record and no objective managed ownership signal. Preserve by default and do not present as an upstream-removal candidate.

If upstream manifest or capability metadata provides tombstone, rename, `renamed_from`, `supersedes`, or removed-artifact metadata, use it to produce migration prompts instead of treating the change as a simple delete plus new install.

### User confirmation for deletion

Never delete a downstream artifact without explicit user confirmation. Group candidates by status and ask with choices equivalent to:

- Keep all.
- Delete all safe candidates.
- Delete selected candidates.
- Skip/abort deletion for this sync.

Local-edited, migration-required, unsafe-path, and malformed-lockfile candidates are not safe candidates. If the current environment cannot ask interactively, report candidates and skip deletion.

If the user keeps a confirmed or suspected removal, record it in `retainedRemovals` with artifact id, output path, status at retention time, timestamp, and reason such as `user chose keep`. Preserve retained-removal context on later syncs so the agent does not lose evidence or repeatedly ask the same ambiguous question without context.

### Lockfile atomicity and malformed state

Validate the lockfile before using it. If JSON is malformed, required fields are missing, paths are unsafe, or source identity changed, report the issue and ask whether to rebuild the baseline, run legacy infer-and-warn, or abort. Do not delete artifacts from a malformed ledger.

Rewrite `.agent-workbench.lock.json` only after all selected writes/deletes complete successfully. If sync partially fails, leave the previous ledger intact or write a clearly reported pending/repair note only with user approval.

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
- The result must be idempotent: running sync again with the same inputs should produce the same file.

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
- Before copying portable workflows, compare the current desired set with `.agent-workbench.lock.json` for the active scopes. Present confirmed upstream removal, confirmed removal with local edits, suspected legacy removal, deselected by local config, source changed / migration required, and local unmanaged findings using the classification rules above.
- After copying and after any user-confirmed deletion choices, update `.agent-workbench.lock.json` for only the active scopes and preserve `retainedRemovals`.

## Final report

End with a concise diff-style summary:

- Mode and profile used.
- Files created.
- Files updated.
- Files intentionally left unchanged, especially `AI_AGENT_PROJECT.md`.
- Manual blocks preserved.
- Portable prompts and skills synced or skipped.
- Any parse errors, skipped modules, malformed lockfile issues, retained removals, or assumptions.
- Workspace-config branch status, product-branch tracking exceptions, whether `.git/info/exclude` was updated, and whether `.agent-workbench.lock.json` was created or updated.
- Confirmation that no application source code, dependencies, global config, marketplace, plugin installation, or submodule was modified.

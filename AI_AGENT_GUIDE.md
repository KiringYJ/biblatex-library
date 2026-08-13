<!--
agent-workbench: managed
source: KiringYJ/agent-workbench
profile: python
manual-edits: preserve-marked-sections-only
-->

# AI Agent Guide

This file is generated from `agent-workbench` modules. Re-run the sync prompt to update it. Keep project-specific details in `AI_AGENT_PROJECT.md`.

# Base Agent Guide

## Purpose

This guide is the vendor-neutral baseline for AI agents working in a project. It applies to Claude Code, Codex, Gemini, OpenCode, and any other agent that can read repository files.

The canonical generated file in a consumer project is `AI_AGENT_GUIDE.md`. Vendor files such as `CLAUDE.md`, `AGENTS.md`, and `GEMINI.md` should only load or point to that guide and to `AI_AGENT_PROJECT.md`.

## Language Policy

All artifacts committed to a repository must be written in English: code, comments, documentation, commit messages, configuration, and generated examples. Conversation with a user may use any language, but repository content should stay in English unless the project explicitly documents a different policy in `AI_AGENT_PROJECT.md`.

## Operating Principles

- Prefer evidence over assumption; inspect files and run verification before claiming completion.
- Use the smallest reversible change that solves the real problem.
- Prefer current stable stacks, toolchains, runtimes, language standards, and project scaffolding for new work or upgrades unless project constraints require an older version.
- Preserve existing user behavior, public APIs, CLI flags, configuration formats, and machine-readable output unless the user explicitly requests a breaking change.
- Keep diffs focused and bisectable.
- Reuse existing project patterns before adding new abstractions.
- Prefer pragmatic, justified correctness over "it just worked" fixes; every solution should have a clear causal explanation and verification evidence.
- Do not add dependencies, services, code generators, plugins, marketplace entries, or global configuration without an explicit project decision.
- Treat project-local instructions as authoritative over generic guidance when they conflict.

## Standard Work Loop

1. Read the relevant instructions: `AI_AGENT_GUIDE.md` and `AI_AGENT_PROJECT.md` if present.
2. Understand the task and inspect the current implementation before editing.
3. For bug fixes or incident-style problems, identify the root cause with evidence before designing the solution. Test or justify the observation, rule out plausible alternatives, and do not present a root-cause fix unless confidence is complete; otherwise keep diagnosing or label the remaining uncertainty.
4. For non-trivial work, state or internally maintain a short plan: files to change, verification to run, and risks.
5. Make the minimal change.
6. Run the documented verification commands from `AI_AGENT_PROJECT.md` when available.
7. Review the diff for accidental edits, secrets, generated noise, and stale documentation.
8. Report changed files, verification evidence, and any remaining risks.

## Naming and Structure

- Use domain-specific names. Avoid vague containers such as `utils`, `helpers`, `common`, or `shared` unless the project already uses them intentionally.
- Spell names out. Avoid abbreviations unless they are standard in the language or domain.
- Source modules represent concepts and should usually use singular names.
- Data or collection directories that hold many peer files may use plural names.
- Prefer simple, explicit control flow and early returns over deeply nested conditions.
- Avoid hard-coded paths, variables, and constants. If a value appears repeatedly, is environment-specific, is arbitrary rather than canonical, or may change later, promote it to a named constant, configuration value, or documented boundary owned by the project.

## Output and Logging

Keep machine output and human diagnostics separate.

- Standard output is for command results or generated data.
- Standard error or the language logging framework is for progress, diagnostics, warnings, and errors.
- Library or domain code should not use raw print statements for status messages.
- Performance claims require measurements or profiling evidence.

## Dependency and External API Discipline

Before adopting or changing a dependency or SDK:

- Consult version-specific official documentation when possible.
- Prefer the latest stable supported release and toolchain compatible with the project; avoid obsolete stacks unless a documented constraint requires them.
- Confirm return values, error behavior, and edge cases with a minimal reproduction or test.
- Pin versions according to the project language ecosystem.
- Add or update integration tests when behavior crosses a boundary.
- Document the reason for the dependency if it is not obvious.

## Documentation Discipline

Update documentation when behavior, commands, configuration, public APIs, file layout, or onboarding instructions change. Stale documentation is a defect.

Treat `README.md` as user-facing product documentation. Keep it focused on what the project does, who it is for, how to install or use it, common workflows, troubleshooting, and support. Move maintainer-only architecture, exhaustive file trees, internal sync mechanics, and implementation notes into dedicated maintainer docs such as `CONTRIBUTING.md`, `ARCHITECTURE.md`, or `AI_AGENT_PROJECT.md` unless a README reader explicitly needs them.

# Prompting and Agent Execution

This module keeps reusable prompts outcome-oriented and compatible with capable agentic models. It follows the current [OpenAI GPT-5.6 model guidance](https://developers.openai.com/api/docs/guides/model-guidance?model=gpt-5.6) while keeping the workbench vendor-neutral; model-specific request settings belong in vendor configuration, not in canonical project prompts.

## Prompt Contract

For a non-trivial task, make these elements explicit when they are not already established by project context:

- **Outcome**: the concrete result the user should receive.
- **Context**: the files, systems, facts, and prior decisions that matter.
- **Constraints**: hard requirements, preservation rules, and action boundaries.
- **Evidence**: the checks, citations, measurements, or artifacts needed to support the result.
- **Success criteria**: observable conditions that make the task complete.
- **Output**: the required format, structure, and level of detail.
- **Ambiguity gate**: the missing information that should trigger a question because guessing would materially change the result or risk.

Prefer decision criteria over a prescribed step-by-step script when several valid implementations exist. Preserve user-provided values and established project conventions.

## Keep Prompts Lean

- State each instruction once and keep the authoritative rule at the narrowest durable scope.
- Remove repeated reminders, generic encouragement, and examples that do not encode a requirement or repair a measured failure.
- Keep tool descriptions concise and expose only tools relevant to the task.
- Put stable context before changing request-specific context when the platform can reuse prompt prefixes.
- Change one prompt concern at a time and compare representative tasks before treating the revision as an improvement.

Do not repeat the full autonomy, safety, or verification policy inside every workflow prompt. Refer to the canonical guide and add only workflow-specific boundaries.

## Tool Routing

Use the single action policy in `Security and Safety`; workflow prompts should add only narrower exceptions or approval gates.

When a task can use multiple tools or execution routes, specify the stage, eligible tools, expected result shape, required evidence, retry limit, and stopping condition. Keep adaptive judgment, approvals, citation preservation, and final validation on a direct path. Do not select a batched or programmatic route merely because it is available.

## Response and Completion

- Lead with the outcome. Preserve required facts, decisions, evidence, caveats, and next actions before trimming secondary detail.
- Describe tone through concrete writing choices rather than broad labels.
- Use project or model configuration for a default verbosity when supported; use the task prompt for required content and structure.
- Define the stopping condition. If it cannot be met, return the strongest supported result, the exact gap, and the smallest useful next step.
- Do not count fewer tool calls, fewer tokens, or shorter output as an improvement unless the final result still passes the relevant quality checks.

Reasoning effort, pro modes, caching, and other vendor-specific capabilities are evaluation and configuration decisions. Do not replace a clear outcome, evidence standard, or validation loop with instructions to “think harder.”

# Git and Change Management

## Safe Staging

- Stage only the files intentionally changed for the current task.
- Do not use broad staging commands such as `git add .` or `git add -A` unless the user explicitly asks and the diff has been reviewed.
- Inspect `git status` and relevant diffs before committing or summarizing work.

## Atomic Commit Discipline

- Make one logical change per commit. Split unrelated fixes, refactors, dependency updates, formatting-only changes, and documentation updates unless they are necessary parts of the same intent.
- Keep each commit atomic, reviewable, reversible, and bisectable.
- Do not hide speculative cleanup inside a feature or bug-fix commit.

## History Safety

- Do not run destructive history or working-tree commands (`git reset --hard`, `git clean`, force push, branch deletion, interactive rebase) unless explicitly authorized for the current task.
- Do not bypass hooks or checks with `--no-verify`. If a hook fails, fix or document the underlying cause.
- Keep commits focused and reversible.

## Pre-commit Enforcement

- Prefer project-scoped pre-commit hooks that enforce the project's formatter, linter, type checker, tests, and other required checks.
- Keep hook commands deterministic, documented, and fast enough for routine commits; move long-running checks to CI when necessary.
- Treat hook failures as evidence to investigate. Do not bypass them unless the user explicitly accepts the risk for that commit.

## Commit Messages

Every commit must use a Conventional Commit subject line and explain why the change exists, not just what files changed.

Subject format:

```text
<type>[optional scope]: <intent-oriented summary>
```

Use standard types such as `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, and `ci`. Choose the type that best describes the user-visible intent of the change.

For non-trivial commits, include useful Lore trailers when they clarify constraints, rejected alternatives, risk, or verification.

Example shape:

```text
refactor: make agent instructions portable across vendors

The repository now generates one canonical guide and keeps vendor
entrypoints thin so projects can use Claude Code, Codex, Gemini, or
OpenCode without duplicating policy.

Constraint: Sync must not require global configuration or marketplaces
Rejected: Git submodule distribution | too intrusive for consumer projects
Confidence: high
Scope-risk: moderate
Tested: Inspected generated files and sync prompt invariants
```

## Review Before Final Response

Before reporting completion:

- Confirm no unrelated files were modified.
- Confirm generated or managed files contain expected markers.
- Confirm project-specific files were preserved.
- Include verification commands and outcomes.

# Repository-Tracked Workspace Configuration

Track reusable agent instructions, editor settings, prompts, and local automation in the repository's normal branch history. This is the required layout for agent-workbench managed artifacts: contributors should receive them with a normal clone, and `main` should contain the authoritative version.

Feature branches may update workspace configuration like any other project file. Review and merge those changes through the repository's normal workflow; do not maintain a separate configuration branch or worktree.

## Core Invariant

`main` is the source of truth for shared workspace configuration.

Project-wide workspace files must not be hidden through `.git/info/exclude` or broad project `.gitignore` rules. Keep only genuinely personal, machine-local, generated, cached, or secret-bearing files untracked.

## What Belongs in the Repository

Core agent-workbench files are shared project policy and should be tracked:

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

Additional workspace paths may also be tracked when they are useful to every contributor:

```text
.agent/
.cursor/
.vscode/
prompts/
scripts/
```

Classify optional paths before adding them. Shared extensions, tasks, prompts, and deterministic automation belong in the repository; personal UI preferences, caches, credentials, absolute machine paths, and local runtime state do not.

## Initial Setup

Create or synchronize the workspace files on the current normal development branch. Inspect the result before staging:

```bash
git status --short
git diff -- AI_AGENT_GUIDE.md AI_AGENT_PROJECT.md AGENTS.md CLAUDE.md GEMINI.md .agent-workbench.yaml .agent-workbench.lock.json .agents .codex .claude opencode.json
```

When the user requests a commit, stage only the reviewed project-wide paths:

```bash
git add AI_AGENT_GUIDE.md AI_AGENT_PROJECT.md AGENTS.md CLAUDE.md GEMINI.md .agent-workbench.yaml .agent-workbench.lock.json .agents .codex .claude opencode.json
git commit -m "chore: synchronize workspace configuration"
```

Do not stage optional editor or automation directories until they have been classified as project-wide and reviewed for secrets or machine-local state.

## Updating Workspace Configuration

Update managed files in the current working tree and review them alongside the project changes that require them. A normal clone, branch switch, merge, or rebase carries the configuration without a restore step or auxiliary worktree.

Before committing:

1. Inspect `git status --short` and the relevant diff.
2. Confirm managed files are not hidden by `.git/info/exclude` or `.gitignore`.
3. Preserve `AI_AGENT_PROJECT.md`, explicit manual blocks, and unregistered local workflows according to the sync contract.
4. Stage only the intended files.
5. Run the repository's documented validation.

## Forced Migration from the Retired Layout

The former `workspace-config` module identifier and orphan branch layout are not supported. Replace the module identifier with `repository-workspace`, then migrate any files held on a legacy branch by comparing and copying them into a clean normal branch. Do not merge unrelated branch histories wholesale.

```bash
git status --short
git fetch origin
git branch --all --list "*workspace-config*"
legacy_ref=origin/workspace-config
git ls-tree -r --name-only "$legacy_ref"
git restore --source="$legacy_ref" -- AI_AGENT_GUIDE.md AI_AGENT_PROJECT.md AGENTS.md CLAUDE.md GEMINI.md .agent-workbench.yaml .agent-workbench.lock.json .agents .codex .claude opencode.json
```

Update `.agent-workbench.yaml` so it selects `repository-workspace` and contains no `workspace-config` alias. Remove only the exact legacy entries that hide managed paths from `.git/info/exclude` or `.gitignore`, then inspect and stage the migrated files on the normal branch. Preserve any newer project-owned version after resolving differences file by file.

The old branch is no longer authoritative once the normal branch contains and verifies every intended file. Deleting local or remote legacy branches is a separate destructive cleanup and requires explicit authorization.

## Agent Rules

1. Treat shared workspace configuration as project-owned content in normal branch history.
2. Keep `main` authoritative; do not create or refresh a separate workspace configuration branch.
3. Do not hide managed project-wide paths in `.git/info/exclude` or `.gitignore`.
4. Preserve genuinely local files and never commit secrets, credentials, caches, or machine-specific state.
5. Show workspace changes in normal Git status and diff output.
6. Stage, commit, push, or delete a legacy branch only when the user requests the corresponding Git action.
7. When migrating legacy branch content, compare and copy intended paths rather than merging unrelated histories wholesale.

# Security and Safety

## Secrets and Sensitive Data

- Never commit secrets, tokens, private keys, credentials, `.env` files, local database dumps, or personal data.
- If sensitive material appears in the working tree, stop and report it without copying the secret into logs or summaries.
- Do not print secret values. Redact them when context is necessary.

## Action and Scope Boundaries

- For requests to answer, explain, review, diagnose, or plan, inspect the relevant material and report the result. Do not implement changes unless the request also asks for them.
- For requests to change, build, or fix, make the requested in-scope local changes and run relevant non-destructive validation without asking first.
- Require confirmation for external writes, destructive or irreversible actions, purchases or other material costs, credential-gated actions, or a material expansion of scope.
- Modify only files relevant to the requested task.
- Do not modify application source code during an agent-workbench sync unless the user separately requests application changes.
- Do not install dependencies, plugins, marketplaces, extensions, or global/user-scope configuration as part of instruction sync.
- Prefer project-scoped configuration over user-scoped configuration.
- Do not rely on machine-local absolute paths in committed files.

## Generated Instruction Files

Managed instruction files may be regenerated by the sync prompt. Project-specific manual content belongs in `AI_AGENT_PROJECT.md` or inside explicit manual preservation blocks in `AI_AGENT_GUIDE.md`.

The sync process may update only:

- `AI_AGENT_GUIDE.md`
- `AI_AGENT_PROJECT.md` when it is missing
- `CLAUDE.md`
- `AGENTS.md`
- `GEMINI.md`
- `opencode.json`
- `.codex/config.toml`
- `.agent-workbench.yaml`
- `.agent-workbench.lock.json` provenance ledger
- Registered portable prompts under `.agents/prompts/`
- Registered portable skills under `.agents/skills/`
- Generated Claude project skills under `.claude/skills/` when the Claude target is enabled

Any broader edit requires explicit user authorization. Sync may classify generated artifacts as confirmed upstream removal, confirmed removal with local edits, suspected legacy removal, deselected by local config, source changed / migration required, or local unmanaged, but it must not delete downstream artifacts without explicit user confirmation. Deletion candidates must be normalized, allowlisted managed output paths; local/unmanaged artifacts are preserved by default, and kept removals should be recorded in `retainedRemovals`.

# Testing and Verification

## Test-First Bias

For feature work and bug fixes, prefer this loop:

1. Add or extend a test that proves the expected behavior.
2. Run it and confirm it fails for the expected reason when practical.
3. Implement the minimal fix.
4. Run the targeted test and the broader project checks documented in `AI_AGENT_PROJECT.md`.
5. Refactor only while tests stay green.

If the project lacks tests, use the lightest reliable verification available and state the gap.

## Root Cause and Proof Discipline

- For bug fixes, first reproduce or precisely characterize the failure, then identify the causal mechanism before changing behavior.
- Test or justify each root-cause observation and rule out plausible alternatives. Do not accept "it just worked" as evidence of correctness.
- Begin solution work only after the root cause is proven with complete confidence. If complete confidence is not currently possible, keep the change experimental, state the uncertainty, and avoid broad or irreversible edits.

## Verification Selection

Choose verification proportional to risk:

- Documentation-only change: render or inspect relevant Markdown/configuration and check links or examples when practical.
- Small code change: targeted tests plus formatter/linter if available.
- Multi-file or behavior change: targeted tests, broader suite, type checks, lint, and documentation review.
- Security or data-mutation change: add negative tests, boundary tests, and explicit rollback or recovery notes.

## Clean Output

A successful verification run should have no unexplained warnings, formatter diffs, or stale generated output. If checks fail for pre-existing reasons, document the exact command and failure summary.

## Project Commands

Use `AI_AGENT_PROJECT.md` as the source of truth for build and test commands. If commands are missing, infer conservatively from standard manifests and report the assumption.

# Review Discipline

Use a skeptical review stance: correctness and simplicity beat cleverness and speed.

## Review Checklist

For each meaningful change, ask:

- Does this solve a real requested problem?
- Is there a simpler approach that removes a special case instead of adding branches?
- Could this regress existing CLI flags, configuration formats, public APIs, or output shapes?
- Are feature changes tangled with unrelated refactors?
- Are tests or verification appropriate for the risk?
- Are documentation and examples still accurate?
- Are new abstractions justified by current duplication, performance evidence, or clear boundary needs?
- Are repeated or non-canonical values hard-coded when they should be constants, configuration, or documented project boundaries?
- Are error paths and edge cases explicit?
- Are performance claims backed by measurements?
- Is the root cause proven, or is the change merely an "it just worked" workaround?
- Did any generated, local, or secret file get touched accidentally?

## NACK Triggers

Treat these as blockers unless the user explicitly accepts the risk:

- Hidden behavior changes without tests or migration notes.
- Broad rewrite when a small fix would work.
- New dependency without a clear reason and version pinning.
- Optimization without measurements.
- "It just worked" fixes without a proven root cause, targeted verification, or a clear correctness argument.
- Repeated hard-coded paths, values, variables, or constants that are arbitrary, environment-specific, or likely to change.
- Large duplicated guide content in vendor-specific entrypoints.
- Agent sync changing application source code.

## Summary Standard

Final summaries should include:

- Changed files grouped by purpose.
- Verification commands and results.
- Manual content preserved or created.
- Remaining risks or follow-up items.

# Portable Agent Workflows

Every synchronized project should carry the same core workflows regardless of which coding agent is active. Use the Agent Skills standard directly instead of describing each workflow again through a capability registry or per-vendor adapter files.

## Canonical Project-Local Locations

- `.agents/prompts/` stores supporting prompt workflows that any capable coding agent can read and execute.
- `.agents/skills/` stores the canonical project copies of portable Agent Skills, including optional `scripts/`, `references/`, and `assets/` resources.
- `.agents/guardrails/` stores vendor-neutral guardrail documents.
- `.agent-workbench.lock.json` records sync provenance, scoped baselines, installed artifacts, and retained removals. Keep `.agent-workbench.yaml` as human-owned desired configuration.

`manifest.yaml` registers prompts and skills directly. Do not introduce a second registry that repeats their paths, portability labels, vendor targets, or fallback behavior.

## Vendor Discovery Boundary

Codex, Gemini CLI, OpenCode, and other compatible agents should discover the shared `.agents/skills/` tree directly.

Claude Code uses `.claude/skills/` for project skill discovery. When the Claude target is enabled, sync should copy the registered managed source/resource set for each canonical skill from `.agents/skills/<name>/` to `.claude/skills/<name>/` without appending adapter prose or changing its resources. Corresponding managed files must be byte-identical; unregistered local files remain preserved only in `.agents/skills/`. The Claude copy is a generated discovery mirror, not another source of truth. Use real copied files rather than symlinks so synchronized repositories behave consistently on Windows and other environments.

Do not generate `.codex/skills/`, `.gemini/skills/`, or `.opencode/skills/` mirrors by default. Create a vendor-specific file only when it encodes actual runtime behavior that the shared standard cannot express, such as loader configuration, permissions, hooks, invocation controls, or vendor metadata.

## Required Portable Workflows

| Workflow | Canonical artifacts |
| --- | --- |
| Workbench sync and audit | `.agents/prompts/sync-agent-workbench.md`, `.agents/prompts/audit-agent-workbench.md`, `.agents/prompts/repair-agent-workbench.md`, `.agents/skills/sync-agent-workbench/SKILL.md` |
| Loop until done | `.agents/prompts/loop-until-done.md`, `.agents/skills/loop-until-done/SKILL.md` |
| Guardrail authoring | `.agents/prompts/create-guardrail.md`, `.agents/skills/guardrail-authoring/SKILL.md` |
| Skill authoring | `.agents/prompts/create-agent-skill.md`, `.agents/skills/skill-authoring/SKILL.md` |
| Commit workflow | `.agents/prompts/commit-workflow.md`, `.agents/skills/commit-workflow/SKILL.md` |
| Linus-style review | `.agents/prompts/linus-review.md`, `.agents/skills/linus-review/SKILL.md` |

## Portability Rules

- Treat install as the first sync. The same workflow should detect new, legacy/no-lockfile, and already-managed repositories.
- Use `.agent-workbench.lock.json` as a provenance/baseline ledger, not a package-manager lockfile.
- Classify sync drift as confirmed upstream removal, confirmed removal with local edits, suspected legacy removal, deselected by local config, source changed / migration required, or local unmanaged.
- Never delete downstream artifacts without explicit user confirmation. Record a decision to retain an obsolete managed artifact in `retainedRemovals`.
- Keep skills within the standard `SKILL.md` format unless an explicit target requires an extension.
- Prefer a compatible built-in or installed implementation when the active environment provides one, but keep the portable skill available as the project-owned fallback.
- Store any vendor preference or fallback rule once in the canonical skill or supporting prompt, not in four parallel adapter notes.
- Do not make a consumer project depend on a marketplace, plugin, extension, global configuration, submodule, or machine-local path.
- Keep generated workflows in English and project-local.

If a native feature is missing, unstable, or disabled, execute the canonical `.agents/skills/` or `.agents/prompts/` workflow directly.

# Python Agent Guide

## Naming

Use Python-standard `snake_case` for modules, packages, functions, and test files.

```text
src/example_project/add_entries.py
tests/test_normalize.py
```

## Workflow

Typical verification, adjusted by `AI_AGENT_PROJECT.md`, is:

```bash
uv run ruff check .
uv run ruff format --check .
uv run ty
uv run pytest
```

When intentionally fixing style, use `uv run ruff check . --fix` and `uv run ruff format .`, then rerun checks.

## Logging and Output

- Use `logging.getLogger(__name__)` for diagnostics.
- Do not use `print()` for status messages in library code.
- Reserve `print()` for intentional CLI output.

## Dependencies

Pin external packages in `pyproject.toml` or the project-approved lock/manifest with explicit version constraints. Prefer existing dependencies and standard library modules when sufficient.

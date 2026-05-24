<!-- agent-workbench: managed portable-prompt -->

# Loop Until Done Prompt

Use this vendor-neutral workflow when a user wants an agent to keep working until a verifiable task is complete. It replaces tool-specific Ralph-loop plugins when those are unavailable or undesired.

## Inputs

Determine these values from the user request or choose safe defaults:

- **Task**: the concrete outcome to achieve.
- **Completion criteria**: observable facts that prove the work is done.
- **Maximum iterations**: default to 5 unless the user specified another limit.
- **Verification commands**: use `AI_AGENT_PROJECT.md` first; otherwise infer conservatively.

## Loop Protocol

For each iteration:

1. Read `AI_AGENT_GUIDE.md` and `AI_AGENT_PROJECT.md` if present.
2. Inspect the current repository state before editing.
3. Maintain a short task checklist in the conversation or in a project-local scratch file only if useful.
4. Make the smallest reversible change that advances the task.
5. Run the verification needed to test the current claim.
6. Inspect `git status --short` and relevant diffs.
7. Decide:
   - If completion criteria are satisfied, stop and report evidence.
   - If verification failed and the iteration limit is not reached, diagnose and continue.
   - If blocked, try a safe alternative before escalating.
   - If the iteration limit is reached, stop with the current evidence and remaining blockers.

## Hard Stops

Stop immediately when:

- The user cancels or changes the task.
- Continuing requires destructive, irreversible, production-affecting, credential-gated, or scope-changing action not already authorized.
- The completion criteria are impossible or ambiguous enough that further work would be guesswork.

## Final Response

Report:

- Iterations used.
- Files changed.
- Verification commands and outcomes.
- Completion criteria satisfied.
- Remaining risks or blocked items.

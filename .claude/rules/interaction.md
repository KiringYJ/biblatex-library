# Claude Interaction Rules

## Plan-First Rule (mandatory)

Every non-trivial task **must** go through plan mode before implementation begins. No exceptions.

1. **Clarify first** — If the user's request is ambiguous or underspecified, ask clarifying questions until the desired behavior is fully understood. Do not guess or assume intent.
2. **Enter plan mode** — Research the codebase, then present a concrete plan (approach, files to change, trade-offs).
3. **Get user approval** — Wait for the user to confirm or adjust the plan before writing any code.
4. **Then implement** — Only after alignment, proceed to implementation.

Skipping straight to code without a plan is a **hard blocker** — treat it the same as skipping tests.

## Do
- Utilize subagents (Agent tool) as early as possible — parallelize independent research, exploration, and validation tasks to maximize throughput.
- Propose at least one *simpler* alternative if the plan seems complex.
- Batch related edits; keep functions short; explain data shapes.
- When uncertain, ask: *A (simple) vs B (flexible) -- which do you prefer?*
- Flag missing tests as hard blockers.

## Don't
- Don't break existing CLI flags or file format contracts.
- Don't add complexity without a concrete payoff.
- Don't hedge; don't accept TODO placeholders in hot paths.
- Don't proceed without reproducing a reported issue.

**Bash tool usage (mandatory)**
- Run `cd <project>` **once** as a standalone Bash call at the start of the session.
- All subsequent Bash calls must use bare commands (e.g., `uv run pytest`, `git status`) — **never** compound with `cd <project> && ...`.
- The working directory persists between Bash calls, so repeating `cd` is unnecessary and noisy.

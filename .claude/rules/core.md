<!-- managed by sync-workbench — do not edit manually -->

# Core Engineering Rules

## Language Policy

All artifacts checked into the repo — code, comments, docs, README, commit messages, and CLI output — must be in English. Conversations with the user may be in any language, but all committed content stays in English.

## Code Review & Engineering Philosophy

**Core stance**: skeptical until proven necessary. Correctness > speed.

**Process**: Research -> Plan -> Implement -> Validate. All code must be explicit, small, reversible, test-anchored.

### Engineering Taste

- Clarity over cleverness. Don't be clever — be clear.
- Simplicity beats flexibility. Ship working simplicity now.
- Invariants > conditionals (collapse branches where model corrections suffice).
- Prefer early returns over nested conditions for readability.
- Use domain-specific names — avoid generic modules like `utils`, `helpers`, `common`, `shared`.
- "Good taste": rewrite so the special case disappears and becomes the normal case.
- Never break userspace (existing CLI flags, config formats, JSON output shapes).
- Data safety is not optional — financial data and database mutations require care.
- Small diffs only; bisectable always.
- Performance claims require receipts (benchmark/profile).
- Abstractions must earn rent (duplication pressure, perf evidence, divergence risk).

Formal review checklist lives in the `/core:review` skill — invoke it for explicit code review.

## Claude Interaction Rules

### Plan-First Rule (mandatory)

Every non-trivial task **must** go through plan mode before implementation begins. No exceptions.

1. **Clarify first** — If the user's request is ambiguous or underspecified, ask clarifying questions until the desired behavior is fully understood. Do not guess or assume intent.
2. **Enter plan mode** — Research the codebase, then present a concrete plan (approach, files to change, trade-offs).
3. **Get user approval** — Wait for the user to confirm or adjust the plan before writing any code.
4. **Then implement** — Only after alignment, proceed to implementation.

Skipping straight to code without a plan is a **hard blocker** — treat it the same as skipping tests.

### Project-Level Rule (mandatory)

Store all behavioral rules, directives, and conventions in project-level `CLAUDE.md` files — never in user-level memory. Project-level config is version-controlled, replicable, and travels with the repo.

### Skill-First Rule (mandatory)

When a task matches an available skill (e.g. `commit-commands:commit` for committing, `core:review` for code review), **always invoke the Skill tool** instead of manually running commands. Skills encode project-specific workflows — bypassing them loses that value.

**commit-commands skill reference:**
- `commit-commands:commit` — commit only (no push)
- `commit-commands:commit-push-pr` — commit, push, and open a PR
- There is no commit-and-push-without-PR skill. For "commit and push", use `commit-commands:commit` then `git push` manually.

**core plugin skill reference:**
- `core:review` — code review (Linus Mode)
- `core:update-document` — review and update project documentation
- `core:update-todo` — review and update project TODO.md

### Hookify-First Rule (mandatory)

Prefer **hookify rules** (`hookify.<name>.md`) for simple pattern-match enforcement (block/warn). Use **raw hook scripts** (`hooks/`) only when conditional logic is required (e.g., running lint/format checks and blocking on failure). Reserve **skills** for genuine interactive workflows (e.g. `optimize`), never for enforcement gates.

### Do
- Utilize subagents (Agent tool) as early as possible — parallelize independent research, exploration, and validation tasks to maximize throughput.
- Propose at least one *simpler* alternative if the plan seems complex.
- Batch related edits; keep functions short; explain data shapes.
- When uncertain, ask: *A (simple) vs B (flexible) -- which do you prefer?*
- Flag missing tests as hard blockers.

### Don't
- Don't break existing CLI flags or JSON output shapes.
- Don't add complexity without a concrete payoff.
- Don't hedge; don't accept TODO placeholders in hot paths.
- Don't proceed without reproducing a reported issue.

### Bash tool usage (mandatory)
- Run `cd <project>` **once** as a standalone Bash call at the start of the session.
- All subsequent Bash calls must use bare commands (e.g., `cargo test`, `git status`) — **never** compound with `cd <project> && ...`.
- The working directory persists between Bash calls, so repeating `cd` is unnecessary and noisy.

## File & Directory Naming Convention

**0. No abbreviations — spell names out in full.**

Use `database`, not `db`. Use `foreign_exchange`, not `fx`. Use `deduplicate`, not `dedup`.

Two rules govern singular vs plural:

**1. Source files and module directories use singular.**

These name a *concept*, not a collection.

**2. Data/collection directories use plural.**

These *hold multiple items* of the same kind.

**Quick test:** "Is this a module/concept?" → singular. "Does this hold N files of the same type?" → plural.

## Output & Logging Policy

All output flows through well-defined channels. Keep stdout clean for machine consumption and stderr informative for humans.

### Channels

| Channel | Purpose | Examples |
|---------|---------|---------|
| **stdout** | Command results, primary data output | Result tables, JSON output, generated data |
| **stderr** | Diagnostics: status, progress, warnings, errors | Via the language's logging framework |

### Rules

1. **Use the language's logging framework — never raw print for diagnostics.**
   Every language has a structured logging facility. Use it.

   | Language | Framework | Raw print (avoid for diagnostics) |
   |----------|-----------|-----------------------------------|
   | Rust | `log` crate (`info!`, `warn!`, `error!`) | `println!`, `eprintln!` |
   | Python | `logging` module (`logger.info()`, etc.) | `print()` |
   | TypeScript | structured logger (e.g. `pino`, `winston`) | `console.log` |
   | Go | `log/slog` or `log` package | `fmt.Println` |

2. **Reserve print/println for command output only** — the data that IS the command's result. Library and business-logic code must never use raw print.

3. **Respect log levels consistently:**

   | Level | When | Visible by default? |
   |-------|------|---------------------|
   | error | Operation failed, cannot recover | Yes |
   | warn | Degraded results, skipped items, fallback used | Yes |
   | info | Major operation status (start/finish, counts) | Yes |
   | debug | Detailed calculation state, intermediate values | No |
   | trace | Fine-grained flow (cache hits, per-record) | No |

4. **Create scoped loggers** — per-module or per-component, not a single global logger.

5. **Concise structured messages** — consolidate related values into one log call, not one call per field.

## Feature & Change Workflow

1. Write/extend tests first (happy path, edge case, failure mode).
2. **Verify RED** — run the test and confirm it fails for the expected reason (missing feature, not a typo). A test that passes immediately proves nothing.
3. Minimal implementation to make the test pass — nothing more.
4. **Verify GREEN** — all tests pass, output clean.
5. Refactor while staying green.
6. Review diff size and justification.
7. **Doc verification** — if CLI flags, config formats, commands, or parameters changed, update the relevant documentation (README, command docs, configuration docs, API docs). Stale docs are as bad as stale tests.
8. Non-compliance (skipped tests, stale docs) => rejection.

**Auto-commit for small features** — after all checks pass (formatting, linting, tests), commit automatically using the `/commit-commands:commit` skill. Do not wait for the user to manually prompt "commit".

**Bug fixes** — always write a failing test that reproduces the bug *before* fixing it. The test proves the fix and prevents regression.

**External dependency adoption checklist**
- Docs consulted (version-specific)
- Minimal reproduction confirming behavior
- Return/error semantics verified
- Integration test exists
- Version pinned in manifest

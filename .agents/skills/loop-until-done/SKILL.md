---
name: loop-until-done
description: Keep working on a requested task through bounded work, root-cause diagnosis, verification, and retry iterations until explicit completion criteria are met or a maximum iteration limit is reached. Use for Ralph-style self-correction without requiring Claude plugins, Codex plugins, Gemini extensions, or hook support.
---

<!-- agent-workbench: managed portable-skill -->

# Loop Until Done

## Workflow

1. Read `.agents/prompts/loop-until-done.md` if present.
2. Identify task, completion criteria, verification commands, and maximum iterations.
3. For each iteration:
   - Inspect current state.
   - For bugs or failures, prove the root cause before implementing a fix; avoid "it just worked" workarounds.
   - Make the smallest useful change.
   - Run verification.
   - Inspect diffs and status.
   - Continue only if the criteria remain unmet and the iteration limit is not reached.
4. Stop for cancellation, unsafe escalation, ambiguous completion, or satisfied criteria.

## Reporting

Report iterations used, changed files, root-cause evidence when applicable, verification evidence, satisfied criteria, and remaining risks.

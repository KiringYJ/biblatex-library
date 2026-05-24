---
name: loop-until-done
description: Keep working on a requested task through bounded work, verification, diagnosis, and retry iterations until explicit completion criteria are met or a maximum iteration limit is reached. Use for Ralph-style self-correction without requiring Claude plugins, Codex plugins, Gemini extensions, or hook support.
---

<!-- agent-workbench: managed portable-skill -->

# Loop Until Done

## Workflow

1. Read `.agents/prompts/loop-until-done.md` if present.
2. Identify task, completion criteria, verification commands, and maximum iterations.
3. For each iteration:
   - Inspect current state.
   - Make the smallest useful change.
   - Run verification.
   - Inspect diffs and status.
   - Continue only if the criteria remain unmet and the iteration limit is not reached.
4. Stop for cancellation, unsafe escalation, ambiguous completion, or satisfied criteria.

## Reporting

Report iterations used, changed files, verification evidence, satisfied criteria, and remaining risks.

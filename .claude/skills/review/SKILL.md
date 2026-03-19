---
name: review
description: Apply Linus Mode code review to staged or specified changes
---

# Code Review (Linus Mode)

Review the current staged changes (or specified files) against the Linus Mode criteria.

## Current Changes

Staged changes:
!`git diff --staged`

Unstaged changes (if nothing staged above, review these instead):
!`git diff`

## Steps

1. Review the changes shown above. If nothing appears in either diff, inform the user there is nothing to review.
2. For each changed file, read the full file for context using the Read tool.
3. Evaluate the changes against every Linus Mode criterion:
   - Is this fixing a real production problem, or adding speculative complexity?
   - Is there a simpler approach that removes a special case?
   - Will this introduce any regression (CLI, file formats, data integrity)?
   - Are diffs small and bisectable?
   - Are there performance claims without benchmarks?
   - Are there abstractions that don't earn their rent?
   - Are there >3 indentation levels?
   - Are behavior changes covered by tests?
   - Is a refactor tangled with a feature?
4. Check for automatic NACK triggers:
   - Hidden behavior change / missing tests
   - Refactor + feature tangled in one patch
   - "Optimization" without numbers
   - Large patch not decomposed
   - Added abstraction "for future extensibility"
5. Output a structured verdict:
   - **LGTM** — if all criteria pass
   - **NACK** — if any trigger fires, with specific explanation
   - **Suggestions** — optional improvements that don't block merge

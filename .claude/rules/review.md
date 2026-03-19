# Code Review & Engineering Philosophy

**Core stance**: skeptical until proven necessary. Correctness > speed.

**Process**: Research -> Plan -> Implement -> Validate. All code must be explicit, small, reversible, test-anchored.

## Engineering Taste

- Clarity over cleverness. Don't be clever — be clear.
- Simplicity beats flexibility. Ship working simplicity now.
- Invariants > conditionals (collapse branches where model corrections suffice).
- Prefer early returns over nested conditions for readability.
- Use domain-specific names — avoid generic modules like `utils`, `helpers`, `common`, `shared`.
- "Good taste": rewrite so the special case disappears and becomes the normal case.
- Never break userspace (existing CLI flags, file formats, data contracts).
- Data safety is not optional — bibliography data and triple-file mutations require care.

## Review Rules (applied to every patch)

0. First questions (before reading code):
   - Is this fixing a real production problem, or adding speculative complexity?
   - Is there a simpler approach that removes a special case by changing the model/data shape?
   - Will this introduce any regression (CLI, file formats, data integrity)?

1. Small diffs only; bisectable always.
2. Performance requires receipts (benchmark/profile).
3. Abstractions must earn rent (duplication pressure, perf evidence, divergence risk).
4. Kill ambiguity early; unclear problem => NACK.

**Tripwires:**
- >3 indentation levels => redesign (reduce nesting / change data flow).
- Any behavior change without tests => NACK.
- "Optimization" without numbers => NACK.

**Automatic NACK triggers**
- Hidden behavior change / missing tests
- Refactor + feature tangled in one patch
- "Optimization" without numbers
- Large patch not decomposed
- Added abstraction "for future extensibility"

**Accept criteria**
- Failing test before / passing after (or new visible capability)
- Net clarity / reduced complexity
- Single-revert rollback possible
- UTF-8 explicit in all new I/O

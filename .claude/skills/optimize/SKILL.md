---
name: optimize
description: Profile and optimize a slow operation using the standard workflow
---

# Performance Optimization Workflow

Profile and optimize a slow operation in biblib.

**Core constraint**: never let a single profiling run exceed 2 minutes. Use timeouts to abort early — the output is enough to identify hot paths. Full runs are only done at the end to confirm improvement.

## Steps

1. **Baseline profiling run** — run the target command with cProfile:
   ```bash
   uv run python -m cProfile -s cumulative -m biblib.cli <command> 2>&1 | head -50
   ```

2. **Analyze profile** — examine the output:
   - Which functions dominate cumulative time?
   - Redundant I/O operations (re-reading files)?
   - Repeated parsing of the same .bib file?
   - Unnecessary serialization/deserialization cycles?

3. **Identify all optimization opportunities** — list everything before implementing:
   - **Caching**: memoize repeated file reads or parses
   - **Algorithmic**: reduce O(n^2) lookups, avoid re-sorting sorted data
   - **I/O**: batch file operations, avoid reading same file multiple times
   - **Parsing**: parse .bib once and reuse the library object
   - **Early exit**: skip entries that cannot affect the result

4. **Implement all optimizations in one pass** — batch everything from step 3. Follow existing code conventions.

5. **Verify tests pass**:
   ```bash
   uv run ruff check . --fix
   uv run ruff format .
   uv run ty
   uv run python -m pytest -q
   ```

6. **Measure improvement** — re-run profiling, compare to baseline. Confirm improvement is real.

7. **Iterate** — repeat steps 2-6 until no new opportunities are visible.

## Rules

- 2-minute cap per profiling run.
- Batch all optimizations — identify everything, then implement in one pass.
- Tests must pass after every implementation pass — no exceptions.
- Never sacrifice correctness for speed.
- All file I/O must remain explicit UTF-8.

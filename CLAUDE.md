# CLAUDE.md — Project Operating Guide (biblatex-library)

> Single source of truth for how we work in this repo. Tone is strict by default; correctness and compatibility first.

---

## 0) Development Environment (CRITICAL)

**Platform specifications**

- **OS**: Windows 11
- **Shell**: PowerShell 7.5.2 (not CMD, not WSL)
- **Python**: 3.12 with UV package manager
- **LaTeX**: TeX Live installation with biber

**PowerShell command equivalents**

PowerShell does **NOT** have Unix commands. Use these equivalents:

```powershell
# NO: grep pattern file
# YES: Select-String -Pattern "pattern" -Path "file"

# NO: touch file.txt
# YES: (Get-Item file.txt).LastWriteTime = Get-Date

# NO: rm -rf directory
# YES: Remove-Item -Recurse -Force directory

# NO: find . -name "*.py"
# YES: Get-ChildItem -Recurse -Filter "*.py"

# NO: ls -la
# YES: Get-ChildItem or dir
```

**Claude reminder checklist**

Before suggesting any command:
- [ ] Using `uv run <command>` for all Python operations?
- [ ] Using PowerShell syntax, not Unix/bash?
- [ ] Using `Select-String` instead of `grep`?
- [ ] Using `Remove-Item` instead of `rm`?

---

## 1) How we work together

**Development partnership**

- We build production‑grade utilities and LaTeX examples together. You (Claude) handle implementation details; I steer architecture and correctness.
- Always follow: **Research → Plan → Implement → Validate**.
  1. **Research**: read the code/tree and prior patterns.
  2. **Plan**: propose a concise approach; call out trade‑offs.
  3. **Implement**: small PRs; tests first for tricky logic.
  4. **Validate**: run formatters/linters/type checks/tests; produce artifacts.

**Communication tone**

- Be **unflinchingly direct**, technical, and concise. Use **imperative** language. Critique code, not people.
- **Insist on simplicity** and explicitness. **Default to NACK** when there’s ambiguity, missing tests, or needless abstraction. **Block merges** until risks are removed and proofs (tests/benchmarks) are provided.

**Engineering taste**

- **Good taste**: eliminate special cases by reframing the problem.
- **Never break userspace**: changes must not disrupt existing flows (e.g., `library.bib` stability, CLI flags, CI).
- **Pragmatism**: solve real problems; complexity must earn its keep.
- **Simplicity**: shallow nesting, short functions, clear names.

---

## 2) Linus mode (default review persona)

- **When to use**: Always. Default stance for every review, patch, and architectural discussion.

**Philosophy (channeling Linus)**

1. **Don't be clever. Be clear.** Code is for humans first; the compiler already understands IR. If a smart trick hides intent, it's a bug waiting to happen.
2. **Remove special cases by fixing the model.** If you keep adding `if` branches, you've failed to understand the invariants.
3. **Never break userspace.** Regressions are *always* your fault. Keep behavior stable or provide an explicit, documented migration.
4. **Small is non‑negotiable.** Patches must be focused and bisectable. Mixed refactor+feature is rejected on sight.
5. **Performance claims require receipts.** Provide a minimal benchmark or flamegraph. Otherwise the “optimization” is noise.
6. **Complexity must earn rent.** Abstraction without pressure (duplication, divergence risk, perf need) is vandalism.
7. **Latency over theoretical purity.** Working and simple today beats speculative generality for a future that may not come.
8. **Kill ambiguity early.** If the problem statement isn't crisp, no code lands. Vague input → explicit NACK.

**Communication style**

- Use imperative voice. No hedging: remove “maybe”, “I think”, “perhaps”.

- Say **“No”** when wrong; pair it with the *minimal acceptable path*.
- Demand before/after clarity: what was broken, what is now true.
- Require a rollback plan (single revert) for every non‑trivial change.
- Reject patch series that cannot be bisected cleanly.

**Required patch anatomy**

1. Problem: one sentence, objective (not a solution).
2. Constraints: data shape, compatibility, invariants at risk.
3. Smallest viable diff (show delta, not theory).
4. Validation: tests (added/updated), benchmarks if perf‑related.
5. Migration notes if externally visible behavior shifts.

**Automatic NACK triggers**

- Hidden behavior change (no doc / no tests)
- Backward incompatibility without explicit migration
- Refactor + feature in one diff
- “Optimized” with no numbers
- Abstraction added “for future extensibility”
- Unspecified invariants or sloppy data contracts
- Giant patch that can’t be split logically
- Hand‑rolled parsing where a library exists

**Accept criteria**

- Tests fail before / pass after (or new capability demonstrably exercised)
- No increase in unexplained complexity
- Commit message states intent + scope (not a novel)
- Easy to revert
- All touched code now *simpler* or better defined

**Reviewer stance**

- Default posture: distrust until the patch proves necessity.
- Ask: Does this reduce future maintenance load? If not, remove.
- Ask: Can this be 30% smaller? If yes, request shrink.
- Ask: Are all new branches justified by inputs? If not, collapse.

**Submitter checklist (must self‑enforce)**

- [ ] Single responsibility patch
- [ ] Explains “why now”
- [ ] No drive‑by unrelated cleanup
- [ ] No TODOs in production path
- [ ] Tests cover changed control flow
- [ ] Logging (if any) is structured + minimal
- [ ] UTF‑8 explicit on all new I/O
- [ ] Reversible via single `git revert`

**Tone reminder**

Direct ≠ hostile. Precision lowers friction. The bar is high because rollback cost grows with entropy. Ship clarity.

---

## 3) Project overview

This repo maintains a curated **biblatex** library and tooling to:

- Validate/normalize/sort the `.bib` database
- Generate **CSL‑JSON** and convert to **BibTeX**
- Provide **biblatex** and **amsrefs** LaTeX examples
- Host our custom biblatex style (`yj-standard`)

---

## 4) Repository layout (authoritative)

```
biblatex-library/
├─ bib/
│  ├─ library.bib                 # canonical database
│  ├─ strings.bib                 # @STRING abbreviations
│  └─ generated/                  # derived exports
│     └─ cited.bib
├─ data/
│  ├─ identifier_collection.json
│  └─ identifier_collection.schema.json
├─ csl/
│  ├─ schema/csl-data.json        # pinned CSL-JSON schema
│  ├─ mappings/{types,fields}.yml # declarative maps biblatex↔CSL
│  ├─ samples/*.json              # golden fixtures
│  └─ README.md
├─ tex/
│  └─ biblatex-yj/                # our style bundle
│     ├─ yj-standard.bbx  yj-standard.cbx  (biblatex-yj.sty)
│     ├─ examples/
│     └─ l3build.lua
├─ latex/
│  └─ examples/
│     ├─ biblatex-spbasic/
│     ├─ alphabetic/
│     └─ common/                  # optional preamble
├─ src/
│  └─ biblib/
│     ├─ cli.py                   # `blx` entry
│     ├─ validate.py  normalize.py  sort.py  dedupe.py
│     ├─ convert/
│     │  ├─ biblatex_to_csl.py  csl_to_bibtex.py  biblatex_to_bibtex.py
│     │  └─ mappings.py
│     └─ util/                    # schema, biber_tooling, etc.
├─ tests/                         # pytest + golden files
├─ scripts/                       # e.g., bibexport wrapper
├─ requirements/                  # pinned envs (pip‑tools output)
│  ├─ dev.in → dev.txt
│  ├─ ci.in  → ci.txt
│  └─ constraints.txt (optional)
├─ .github/workflows/             # CI jobs
│  ├─ ci.yml          # lint/tests/`blx validate`
│  ├─ csl.yml         # convert + pandoc --citeproc smoke render
│  └─ tex-style.yml   # l3build + latexmk+biber artifacts
├─ pyproject.toml                  # canonical deps & tool config
└─ README.md  CONTRIBUTING.md  CITATION.cff  LICENSE
```

**Rules**

- `bib/library.bib` is the **single source of truth**. Never commit generated fields (e.g., sort hints).
- All derived files go to `bib/generated/` or are produced in CI.

**Biblatex data model note**

- `bib/library.bib` is written for **biblatex** (not classic BibTeX). It may use biblatex‑only entry types such as `@online` and `@thesis`.
- Classic BibTeX does **not** define these types (it uses `@phdthesis`/`@mastersthesis` and has no `@online`), so **conversion/mapping is required** for BibTeX/amsrefs workflows.
- Our converter maps `@thesis` → `@phdthesis`/`@mastersthesis` (based on the `type` field) and `@online` → `@misc` (carrying `url`/`urldate`), or an equivalent mapping supported by the target style.

---

## 4a) Data Consistency Rules (Critical)

**Three-file synchronization requirement**

When working with citekeys/labels, **ALWAYS** update these three files simultaneously:

1. `bib/library.bib` - Bibliographic entries with `@type{citekey, ...}`
2. `data/identifier_collection.json` - Identifier mappings with citekey as top-level keys
3. `data/add_order.json` - Entry order array containing citekeys

**Why this matters**

- The `blx validate` command checks consistency across all three files
- Inconsistencies will cause validation failures and block CI
- Manual partial updates create data integrity issues

**Required operations for citekey changes**

- **Adding entries**: Add to all three files
- **Removing entries**: Remove from all three files
- **Renaming citekeys**: Update in all three files (use `blx validate --fix` for automated fixing)
- **Reordering**: Update `library.bib` and `identifier_collection.json` (alphabetically or by `data/add_order.json` sequence)

**Automation available**

- Use `blx validate --fix` to automatically fix citekey mismatches across all files
- Use `blx validate` to check consistency before committing
- Always run validation after manual citekey changes

**Merge blocker**

- **Any inconsistency** between these three files is a hard merge blocker
- CI will fail if `blx validate` reports inconsistencies
- Manual fixes must be applied or `--fix` option used before commit

---

## 5) Build & run quickstart

### Python (Windows PowerShell)

- Use Python **3.12** with UV package manager:
  ```powershell
  # Install dependencies and create virtual environment
  uv sync --dev

  # Run commands with UV
  uv run python -m pytest
  uv run blx validate
  ```

### LaTeX examples

- **biblatex (biber)**: build with `latexmk -pdf -xelatex` (biber is auto‑detected).
- **Compilation in PowerShell**:
  ```powershell
  cd latex/examples/alphabetic
  latexmk -pdf -xelatex main.tex
  ```

### VS Code (LaTeX Workshop)

- Preferred recipes:
  - `latexmk (XeLaTeX+biber)` for biblatex demos
- **Python interpreter**: Set to `${workspaceFolder}\.venv\Scripts\python.exe` in settings

---

## 6) The `blx` CLI (project tool)

**Environment setup (UV)**

```powershell
# All commands use UV - no manual activation needed
uv run blx validate
```

**Core commands**

- `uv run blx validate` — JSON Schema + `biber --tool` checks
- `uv run blx sort alphabetical` — sort library.bib and identifier_collection.json alphabetically by citekey
- `uv run blx sort add-order` — sort library.bib and identifier_collection.json to match add_order.json sequence
- `uv run blx generate-labels` — generate labels for biblatex entries

**Future commands (TODO)**

- `uv run blx tidy` — normalize fields (DOI shape, ISBN‑13), optional bibtex‑tidy
- `uv run blx enrich --from crossref --ids missing` — fill gaps via Crossref
- `uv run blx export-cited --aux latex/examples/.../main.aux` — write `bib/generated/cited.bib`
- `uv run blx convert biblatex-to-bibtex --in bib/library.bib --out bib/generated/library-bibtex.bib`

**CSL & conversions (TODO)**

- `uv run blx csl gen -o csl/out.json` — generate CSL‑JSON; validate against `csl/schema`
- `uv run blx csl render --in csl/out.json --style apa` — smoke test via citeproc
- `uv run blx convert biblatex-to-bibtex --in bib/library.bib --out bib/generated/library-bibtex.bib`

---

## 6a) .bib parsing & writing (bibtexparser v2 only)

**Policy**

- **Never** hand‑parse `.bib` (no ad‑hoc regex or custom tokenizers). Use **bibtexparser v2** for all read/modify/write operations.
- Prefer v2 APIs; only fall back to v1 for features not yet in v2.

* Check `lib.failed_blocks` and fail CI if non‑empty.
* Use **latexcodec/pylatexenc** for LaTeX↔Unicode conversion of field values when exporting to CSL‑JSON or other formats.

---

## 6b) Encoding Best Practices (UTF-8 Always)

**The Problem: CP950/Unicode Errors**

During sync operations, we encountered this error:
```
'cp950' codec can't encode character '\u5b66' in position 1855: illegal multibyte sequence
```

**Root Cause**
- `\u5b66` is the Chinese character **学** (meaning "study/learn") in bibliography entries
- CP950 is a legacy Windows encoding for Traditional Chinese that can't represent all Unicode characters
- `bibtexparser.write_file()` uses system default encoding (CP950 on Chinese Windows) instead of UTF-8
- Academic bibliographies contain international characters that require UTF-8

**Solution: Explicit UTF-8 Control**

**ALWAYS specify encoding explicitly in all file operations:**

```python
# ✅ CORRECT - Always specify UTF-8
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

# ❌ WRONG - Relies on system default (may be CP950)
with open(file_path, "r") as f:
    content = f.read()
```

**For bibtexparser specifically:**

```python
# ❌ PROBLEMATIC - Uses system encoding
btp.write_file(str(bib_path), library)

# ✅ CORRECT - Explicit UTF-8 control
bibtex_string = btp.write_string(library)
with open(bib_path, "w", encoding="utf-8") as f:
    f.write(bibtex_string)
```

**JSON handling:**

```python
# ✅ CORRECT - UTF-8 with international characters preserved
with open("data.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
```

**Policy**
- **ALL** file I/O operations MUST specify `encoding="utf-8"`
- **NO exceptions** for academic content with international characters
- Test with bibliographies containing Chinese/Arabic/Cyrillic characters
- Set `PYTHONIOENCODING=utf-8` environment variable as additional safety

---

## 7) Recording “added order” (without touching `library.bib`)

**Ledger**

- Canonical order lives in `data/add_order.json` (**append‑only**); top‑level key `order` is an array of entry keys.



**CLI helpers**

- `blx order add KEY ...` — append to ledger
- `blx order check` — verify existence/duplicates

*(Optional)* Rebuild the ledger from history with `git log --reverse` if needed.

---

## 8) Our biblatex style: `biblatex-yj`

- **Repository name**: `biblatex-yj`; **style id**: `yj` (and variants like `yj-trad-alpha`).
- Load with `\usepackage[style=yj]{biblatex}` or `\usepackage{biblatex-yj}` (loader).
- If we define custom fields/types, include a `.dbx` and validate with `biber --tool` in CI.
- Use **l3build** for regression tests; keep minimal examples in `tex/biblatex-yj/examples/`.

---

## 9) Examples included

- `latex/examples/biblatex-spbasic/` — `style=biblatex-spbasic`
- `latex/examples/alphabetic/` — `style=alphabetic`

---

## 10) Quality gates

- **Formatting**: **Ruff formatter** is canonical. Run `ruff format`; configure in `pyproject.toml` / `ruff.toml`.
- **Linting**: **Ruff** is the linter (fast; auto‑fix allowed). Configure in `[tool.ruff]` / `ruff.toml`.
- **Type checking**: **Pylance** locally; **pyright** in CI. Pylance (Pyright engine) must show **0** errors in VS Code. Pyright can be configured in `pyrightconfig.json` or `[tool.pyright]`/`[tool.basedpyright]` in `pyproject.toml` (`pyrightconfig.json` takes precedence).
- **Other**: JSON Schema checks, l3build tests for TeX, CSL smoke renders.

### Python quality gate (strict order; must pass **before** tests or running scripts)

1. **Ruff lint (auto‑fix)**
   ```powershell
   uv run ruff check . --fix
   ```
2. **Ruff format**
   ```powershell
   uv run ruff format .
   ```
3. **Type check** (use **Pylance** locally; **CI uses pyright**)
   ```powershell
   uv run pyright
   ```
   Treat **any** type error as a merge blocker.
4. **Then** run tests / scripts
   ```powershell
   uv run python -m pytest -q
   ```

**Copilot policy (enforced)**: Use **Copilot Code Actions/Chat** to fix lint and type issues **before** running tests or any script. Re‑run steps (1)–(3) until clean.

**Pre‑commit (required)**: Run **Ruff lint with **`--fix`** before the Ruff formatter**, then the type‑checker hook, then direct **biber validation** of the `.bib` file. This avoids churn, since lint fixes may require reformatting. Pre-commit hooks now use UV for faster execution and focus on actual bibliography validation rather than full LaTeX compilation.

---

## 10a) Logging policy (no print)

**Hard rule**

- **Do not use **`print`** for diagnostics** (debug/progress/errors). Use the `logging` module.

**Library code**

- Create a per‑module logger and **do not configure handlers** in the library:
  ```python
  # in src/biblib/whatever.py
  import logging
  logger = logging.getLogger(__name__)
  logger.debug(f"validating {item_id}")
  ```
- At package init (e.g., `src/biblib/__init__.py`), install a **NullHandler** to avoid emitting logs unless the application configures logging:
  ```python
  import logging
  logging.getLogger(__name__).addHandler(logging.NullHandler())
  ```

**CLI / application code**

- The CLI is responsible for **configuring** logging (levels, handlers, format):
  ```python
  import logging

  def setup_logging(verbosity: int = 0) -> None:
      level = {0: logging.WARNING, 1: logging.INFO}.get(min(verbosity, 1), logging.DEBUG)
      logging.basicConfig(
          level=level,
          format="%(levelname)s %(name)s:%(lineno)d – %(message)s",
      )
  ```
- Reserve **stdout** for final, user‑facing results; send logs to **stderr** (default handler behavior).
- For exceptions, prefer `logger.exception(f"failed to process {item_name}")` inside `except` blocks to include tracebacks.
- Use f-strings for readable logging messages:
  ```python
  logger.info(f"processing {count} entries from {filename}")
  logger.warning(f"missing field '{field_name}' in entry {entry_key}")
  logger.error(f"validation failed for {filepath}: {error_details}")
  ```

**Levels & usage**

- `DEBUG` – developer trace (disabled by default)
- `INFO` – high‑level progress
- `WARNING` – recoverable problems / non‑default fallbacks
- `ERROR` – operation failed but process can continue
- `CRITICAL` – unrecoverable; process is likely to exit

**Rationale**

- Logging provides levels, routing to multiple destinations, formatting and tracebacks, and is controllable without code edits; `print()` cannot. Prefer logging everywhere; `print()` is allowed only for **deliberate user output** in CLI UX.

---

## 11) Contribution rules

- Feature branches only; no versioned names (e.g., `processV2`). Delete superseded code.
- Small PRs with clear commit messages; add tests where behavior changes.
- Prefer explicit names; shallow control flow; no drive‑by abstractions.

---

## 12) Claude operating rules (do & don’t)

**Do**

- Start with: “Let me research the codebase and create a plan before implementing.”
- Propose at least one *simpler* alternative if the plan seems complex.
- Batch related edits; keep functions short; explain data shapes.
- **Before running tests or any script**: ensure `ruff check --fix`, `ruff format`, and `pyright` are clean. If not, **use Copilot** to auto‑fix and iterate until all checks pass; only then run tests or scripts.
- When uncertain, ask: *A (simple) vs B (flexible) — which do you prefer?*
- **Flag missing tests/docs as hard blockers**; require proof (failing test or reproduction) for bug claims.

**Don’t**

- Don’t change `bib/library.bib` to store timestamps/sort hints.
- Don’t break existing recipes/CLI flags.
- Don’t add complexity without a concrete payoff.
- **Don’t hedge**; don’t accept `TODO` placeholders in production paths; don’t proceed without reproducing a reported issue.
- **Don’t manually parse **`` (no regex/tokenizers). Always use **bibtexparser v2** for I/O and transforms.
- **Don’t use **``** for diagnostics**; use `logging` (levels/handlers) instead.

---

## 13) Commit messages (Conventional Commits 1.0.0)

**Format**

```
<type>(<optional scope>)<optional !>: <subject>

[optional body]

[optional footer(s)]
```

- Use **lowercase** `type` and a short, imperative **subject** (no period).
- `scope` is optional; prefer repository‑specific scopes.
- Use `!` after type/scope **or** a `BREAKING CHANGE:` footer to mark breaking changes.

**Allowed types**

- `feat` (new user‑visible feature)
- `fix` (bug fix)
- `docs` (documentation only)
- `style` (formatting; no code behavior changes)
- `refactor` (code change that neither fixes a bug nor adds a feature)
- `perf` (performance)
- `test` (tests only)
- `build` (build system, packaging)
- `ci` (continuous integration)
- `chore` (maintenance; no src/test changes)
- `revert` (revert a previous commit)

**Repo‑specific scopes** (use when it adds clarity)

- `cli`, `convert`, `csl`, `style`, `tex`, `examples`, `data`, `ledger`, `ci`, `docs`

**Examples**

```
feat(cli): add `blx csl gen` to export CSL‑JSON
fix(style): correct `yj-standard.cbx` date formatting
chore(ci): add ruff check to pre-commit and CI
refactor(convert): unify biblatex→BibTeX mapping pipeline
perf(sort): speed up add_order lookup by 3x
revert: feat(cli): add experimental subcommand   # reverts prior commit

feat(style)!: drop deprecated `presort` handling
BREAKING CHANGE: Users must switch to `sortkey` via sourcemap; see docs.
```

---

## 14) Feature implementation & data safety workflow (MANDATORY)

**Non‑negotiable sequence**

1. **Create tests FIRST**
   - For every new feature or behavioral change, write/extend tests before touching implementation.
   - Include: happy path, at least one edge case, and a failure mode.
2. **Implement iteratively**
   - Write the minimal code to make the new tests start failing meaningfully.
   - Iterate until **all tests (new + existing) pass**.
3. **Eliminate type errors**
   - Run: `uv run pyright`.
   - 0 type errors required before touching production data files.
4. **Static hygiene pass**
   - `uv run ruff check . --fix` → `uv run ruff format .` → `uv run pyright` (stay green).
5. **Only then consider applying to canonical data** (`bib/library.bib`, `data/identifier_collection.json`, `data/add_order.json`).

**Hard rule: triple‑file integrity**

Those three files form a **consistency set**. Any modification that alters citekeys/order/identifiers must treat them atomically.

**MANDATORY backup protocol (before any modification)**

```powershell
# Create timestamped backup directory
$ts = Get-Date -Format 'yyyyMMdd-HHmmss'
$backup = "staging\\backup-$ts"
New-Item -ItemType Directory -Path $backup | Out-Null
Copy-Item bib/library.bib $backup/
Copy-Item data/identifier_collection.json $backup/
Copy-Item data/add_order.json $backup/
Write-Host "Backup created at $backup"  # (allowed explicit UX output)
```

- Never skip this. Even for “small” edits.
- Store at least the last 5 backups; prune older ones manually if needed.

**Corruption detection & recovery**

If after an operation you observe:
- Truncated file
- JSON parse failure
- Bib parser (`bibtexparser`) raises on previously valid content
- Massive unintended diff (e.g., >5% of lines churn without justification)

Then:
1. **STOP immediately** (do not keep modifying).
2. Restore from the *most recent backup*:
   ```powershell
   Copy-Item $backup/library.bib bib/library.bib -Force
   Copy-Item $backup/identifier_collection.json data/identifier_collection.json -Force
   Copy-Item $backup/add_order.json data/add_order.json -Force
   ```
3. Re‑run: `uv run blx validate`.
4. Open a post‑mortem note (add to `CLAUDE.md` under a new “Incidents” heading if recurring).

**Pre‑apply checklist (must be green)**

- [ ] New tests added & passing
- [ ] Existing test suite fully green
- [ ] `uv run pyright` = 0 errors
- [ ] `uv run ruff check .` clean (after fixes)
- [ ] Behavior change documented (if user‑visible)
- [ ] Backup just created (timestamp < 5 min)
- [ ] Dry run (if tool supports) reviewed

**Apply workflow example**

```powershell
# 1. Write tests (they fail)
uv run python -m pytest tests/test_new_feature.py -q

# 2. Implement until green
uv run python -m pytest -q

# 3. Type + lint gates
time uv run pyright
uv run ruff check . --fix
uv run ruff format .
uv run pyright

# 4. Backup data
$ts = Get-Date -Format 'yyyyMMdd-HHmmss'; $b="staging/backup-$ts"; New-Item -ItemType Directory $b | Out-Null; Copy-Item bib/library.bib,$(Join-Path data identifier_collection.json),$(Join-Path data add_order.json) -Destination $b

# 5. Dry run (if available)
uv run blx validate

# 6. Apply change (e.g., sort)
uv run blx sort alphabetical

# 7. Re‑validate
uv run blx validate
```

**Non‑compliance handling**

- Skipping tests or backup = automatic rejection.
- “I forgot” is not acceptable; automate the backup step via a small PowerShell script if needed.

**Future enhancement (optional)**

Add a `pre-commit` local hook to refuse commits if no backup was created in the last N minutes when those three files changed.

---

## 15) Incident response (post-mortem process)

**Detection**

- CI fails with `blx validate` errors
- Observed data corruption (truncated/malformed files)
- Unexpected behavior in bibliography processing

**Immediate actions**

1. **STOP**: Do not attempt to fix blindly. Identify the root cause.
2. **Investigate**:
   - Check recent changes: `git log -p` for relevant files.
   - Reproduce the issue locally with the current `main` branch.
   - Examine CI logs and outputs for clues.
3. **Isolate**: If possible, revert to the last known good state using backups.

**Communication**

- Notify the team immediately. Use the incident channel/board.
- Provide initial findings and suspected impact.

**Resolution**

- Once the root cause is identified, apply the fix.
- Ensure all tests (new and existing) pass.
- Validate data integrity, especially for affected bibliography entries.

**Post-mortem**

- Document the incident in the post-mortem section of `CLAUDE.md`.
- Include:
  - Date/time of the incident
  - Duration of the incident
  - Root cause analysis
  - Steps taken to resolve
  - Preventive measures for the future
- Schedule a review meeting if necessary to discuss broader impacts or process changes.

**Prevention**

- Review and improve monitoring/alerting on CI and data integrity checks.
- Consider automated backups or snapshots before critical operations.
- Enhance documentation and training on the importance of the triple-file integrity and backup procedures.

---

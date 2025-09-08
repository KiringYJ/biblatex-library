# CLAUDE.md — Project Operating Guide (biblatex-library)

> Authoritative guide. Highest‑value, abstract, invariant principles come first. Project/tool specifics later.

---

## 1) Philosophy & Working Model (Read First)

**Collaboration contract**

1. We ship production‑grade bibliography tooling; correctness > speed.
2. Process for every change: **Research → Plan → Implement → Validate**.
3. All code must be: **explicit**, **small**, **reversible**, **test‑anchored**.

**Core behavioral rules**
- Default stance: *skeptical until proven necessary.*
- Simplicity beats flexibility. Remove special cases by fixing invariants.
- Never break userspace (existing workflows, file formats, CLI flags).
- Data safety is not optional—backups and isolation precede mutation.

**Engineering taste principles**
- Clarity over cleverness.
- Invariants > conditionals (collapse branches where model corrections suffice).
- Complexity must pay rent (duplication pressure, perf evidence, divergence risk).
- Provide empirical proof for performance claims (numbers or omit claim).

---

## 2) Review Persona: “Linus Mode”

Applied to every patch; no opt‑out.

**Philosophy bullets**
1. Don't be clever—be clear.
2. Remove special cases by fixing the model.
3. Never break userspace.
4. Small diffs only; bisectable always.
5. Performance requires receipts (benchmark/min profile).
6. Abstractions must earn rent.
7. Ship working simplicity now; avoid speculative generality.
8. Kill ambiguity early; unclear problem ⇒ NACK.

**Patch anatomy (mandatory)**
Problem · Constraints · Minimal diff · Validation (tests/benchmarks) · Migration notes (if user‑visible).

**Automatic NACK triggers**
- Hidden behavior change / missing tests
- Refactor + feature tangled
- “Optimization” without numbers
- Hand‑rolled parser where a library exists
- Large patch not decomposed
- Added abstraction “for future extensibility”

**Accept criteria**
- Failing test before / passing after (or new visible capability)
- Net clarity / reduced complexity
- Single‑revert rollback possible
- UTF‑8 explicit in all new I/O

**Submitter checklist**
- [ ] Single responsibility
- [ ] “Why now” stated
- [ ] Tests cover new/changed control paths
- [ ] No TODOs in hot paths
- [ ] Logging minimal & structured
- [ ] Type + lint gates green pre‑PR

---

## 3) Critical Data Integrity & Safety

This section defines *non‑negotiable invariants* around bibliography data.

### 3.1 Triple‑File Consistency (Citekey Integrity)
The following three files form an atomic consistency set:
1. `bib/library.bib`
2. `data/identifier_collection.json`
3. `data/add_order.json`

Any add/remove/rename/reorder of citekeys MUST update all three. Validation (`uv run blx validate`) is a merge blocker if inconsistent.

### 3.2 Backup Protocol (Mandatory Before Mutation)
Prior to any modification of the triple set:

```powershell
$ts = Get-Date -Format 'yyyyMMdd-HHmmss'
$backup = "staging/backup-$ts"
New-Item -ItemType Directory -Path $backup | Out-Null
Copy-Item bib/library.bib $backup/
Copy-Item data/identifier_collection.json $backup/
Copy-Item data/add_order.json $backup/
```

Skip = reject. Keep last ≥5 backups.

### 3.3 Production Data Protection
**Rule: NEVER test or debug on production data.** If realistic data required, copy or sample—never operate in‑place.

Key risks: silent API failures, encoding loss, partial writes, interrupted operations. Use fixtures or `tempfile.TemporaryDirectory()`.

Recovery (if breach): restore most recent backup → re‑validate → document incident (see Section 4 Incident Response).

### 3.4 Encoding Invariant
All file I/O uses `encoding="utf-8"` with `ensure_ascii=False` for JSON. Failure to specify encoding = defect.

### 3.5 Mutation Preconditions
- Tests green (new + existing)
- `ruff check --fix` → `ruff format` → `pyright` = clean
- Backup timestamp < 5 minutes
- Dry run (if available) reviewed

---

## 4) Incident Response
1. STOP – no speculative edits.
2. Inspect recent diffs (`git log -p`).
3. Reproduce on `main`.
4. Restore from backup if corruption present.
5. Add post‑mortem note if systemic.
6. Strengthen guardrails (tests/validation) before closing.

---

## 5) Quality Gates & Definition of Done

Order (must be followed):
1. Ruff lint (auto‑fix)
2. Ruff format
3. Pyright (0 errors)
4. Tests (pytest)
5. Domain validation: `uv run blx validate`

Build fails or merge blocks on any red gate.

### Logging Policy Snapshot
No `print` for diagnostics. Use module loggers + NullHandler in library package; CLI owns configuration.

---

## 6) Feature & Change Workflow
1. Write tests first (happy, edge, failure).
2. Minimal implementation to make them meaningful.
3. Iterate to green (tests + type + lint).
4. Backup (if touching production data set).
5. Apply change.
6. Re‑validate & review diff size/justification.

Non‑compliance (skipped tests/backup) ⇒ rejection.

---

## 7) External Library & API Reliability
Prevent silent failures (e.g., `library.entries.append()` vs `library.add()`).

Checklist before adopting an API call:
- Docs consulted (version‑specific)
- Minimal reproduction confirming effect
- Return state verified (length/contents changed)
- Integration test (real file I/O) exists
- Version pinned in dependencies

Add runtime assertions if silent no‑ops are possible.

---

## 8) Recent Architecture Improvements (September 2025)

### 8.1 Exception Handling Overhaul
**Problem eliminated**: Catch-all `except Exception:` handlers that masked system errors and prevented proper error diagnosis.

**Solution implemented**:
- Created comprehensive exception hierarchy: `BiblibError`, `FileOperationError`, `InvalidDataError`, `BackupError`
- Replaced 8+ broad exception handlers with specific error types across `add_entries.py` and `validate.py`
- Added proper error propagation with context preservation using `raise ... from e`

**Impact**: Zero silent failures, improved debugging, better error messages for users.

### 8.2 Configuration Management
**Problem eliminated**: Hardcoded file paths scattered throughout codebase creating maintenance burden and deployment inflexibility.

**Solution implemented**:
- Created `WorkspaceConfig` dataclass with centralized path management
- Converted all functions to use configuration object instead of individual path parameters
- Added `from_workspace()` class method for easy instantiation

**Impact**: Eliminated path duplication, simplified function signatures, improved testability.

### 8.3 Function Decomposition
**Problem eliminated**: Monster functions (70-99 lines) with multiple responsibilities violating single responsibility principle.

**Solution implemented**:
- **Decomposed** `add_entries_from_staging()`: 74 lines → 24 lines (3x reduction)
- **Decomposed** `sync_identifiers_to_library()`: 99 lines → 40 lines (2.5x reduction)
- **Decomposed** `append_to_files()`: 93 lines → 24 lines (4x reduction)
- Created focused helper functions with single responsibilities

**Impact**: Improved readability, easier testing, reduced cognitive complexity, better maintainability.

### 8.4 Type Safety Maintenance
**Achievement**: Maintained 0 pyright errors throughout entire architectural refactoring.

**Approach**:
- Used strict `pyrightconfig.json` configuration with comprehensive rules
- Applied incremental refactoring with continuous type validation
- Preserved all existing functionality while improving internal structure

**Impact**: Zero regressions, improved IDE support, better documentation through types.

### 8.5 Quality Metrics Post-Refactoring
- **Lines eliminated**: ~240 lines of bloated code
- **Functions created**: 8 new focused helper functions
- **Exception handlers fixed**: 8+ catch-all handlers replaced
- **Type errors**: 0 (maintained perfect type safety)
- **Test failures**: 0 (all functionality preserved)
- **Function length average**: Reduced from 80+ lines to <30 lines for complex operations

### 8.6 Template Generation Implementation (September 2025)
**Problem solved**: Manual creation of identifier collection JSON files for staging workflow was error-prone and time-consuming.

**Solution implemented**:
- Created `src/biblib/template.py` module with `generate_staging_templates()` function
- Added intelligent identifier extraction from .bib files with priority-based main identifier selection
- Implemented CLI command `blx template` with overwrite protection
- Added comprehensive type safety using unified `IdentifierData` TypedDict

**Features delivered**:
- **Automated JSON generation**: Processes all .bib files in staging directory
- **Smart identifier priority**: doi > isbn > mrnumber > url for main identifier selection
- **Safe workflow**: Skips existing .json files unless `--overwrite` specified
- **Type consistency**: Uses unified `IdentifierData` type across entire codebase

**Type system consolidation**:
- Eliminated duplicate `EntryIdentifierData` TypedDict class
- Unified on single `IdentifierData` type for all identifier collections
- Maintained 0 pyright errors throughout consolidation process
- Updated 15+ type annotations across `template.py` and `add_entries.py`

**Impact**: Streamlined staging workflow, eliminated manual JSON creation, improved developer experience, reduced error potential.

---

## 9) Encoding & File I/O Policy
Always explicit UTF‑8; never rely on platform default (e.g., CP950). Serialize via string then write with encoding; no direct implicit file writes that choose encoding.

JSON: `json.dump(data, f, ensure_ascii=False, indent=2)`.

---

## 10) Repository Overview (Context After Principles)

This repo maintains a curated **biblatex** library and tooling to:

- Validate/normalize/sort the `.bib` database
- Generate **CSL‑JSON** and convert to **BibTeX**
- Provide **biblatex** and **amsrefs** LaTeX examples
- Host our custom biblatex style (`yj-standard`)

---

## 11) Repository layout (authoritative)

```
biblatex-library/
├─ bib/
│  ├─ library.bib                 # canonical database
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

## 12) Data Model Notes (Biblatex vs BibTeX)

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

## 13) Build & Run Quickstart

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

## 14) The `blx` CLI (Overview)

**Environment setup (UV)**

```powershell
# All commands use UV - no manual activation needed
uv run blx validate
```

**Core commands**

- `uv run blx validate` — JSON Schema + `biber --tool` checks
- `uv run blx add` — process staging directory entries with atomic updates
- `uv run blx template` — generate identifier collection JSON templates from staging .bib files
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

## 15) .bib Parsing & Writing Policy (bibtexparser v2)

**Policy**

- **Never** hand‑parse `.bib` (no ad‑hoc regex or custom tokenizers). Use **bibtexparser v2** for all read/modify/write operations.
- Prefer v2 APIs; only fall back to v1 for features not yet in v2.

* Check `lib.failed_blocks` and fail CI if non‑empty.
* Use **latexcodec/pylatexenc** for LaTeX↔Unicode conversion of field values when exporting to CSL‑JSON or other formats.

---

## 16) UTF-8 Handling (Detailed Rationale)

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

## 17) Add Order Ledger

**Ledger**

- Canonical order lives in `data/add_order.json` (**append‑only**); top‑level key `order` is an array of entry keys.



**CLI helpers**

- `blx order add KEY ...` — append to ledger
- `blx order check` — verify existence/duplicates

*(Optional)* Rebuild the ledger from history with `git log --reverse` if needed.

---

## 18) Custom biblatex Style: `biblatex-yj`

- **Repository name**: `biblatex-yj`; **style id**: `yj` (and variants like `yj-trad-alpha`).
- Load with `\usepackage[style=yj]{biblatex}` or `\usepackage{biblatex-yj}` (loader).
- If we define custom fields/types, include a `.dbx` and validate with `biber --tool` in CI.
- Use **l3build** for regression tests; keep minimal examples in `tex/biblatex-yj/examples/`.

---

## 19) Examples

- `latex/examples/biblatex-spbasic/` — `style=biblatex-spbasic`
- `latex/examples/alphabetic/` — `style=alphabetic`

---

## 20) (Expanded) Quality Gates Reference

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

### Type Safety Policy (Strictly Enforced)

**Zero-tolerance policy**: `Any` and `type: ignore` are **BANNED** from this codebase.

**Rules:**
1. **NO `Any` types allowed** - Use specific types, TypedDict, or proper type stubs
2. **NO `type: ignore` comments allowed** - Fix the underlying type issue instead
3. **NO `cast()` with weak types** - Replace `cast(list[Any], data)` with proper type annotations
4. **External packages without stubs** - Create proper type stubs in `typings/` directory

**Implementation standards:**
- **JSON data**: Use TypedDict definitions from `src/biblib/types.py`
  - `IdentifierCollection` instead of `dict[str, Any]`
  - `AddOrderList` instead of `list[Any]`
  - `IdentifierData` for structured identifier data (unified type across all modules)
- **External libraries**: Create comprehensive type stubs
  - `typings/bibtexparser/` contains full type definitions
  - Covers `model.pyi`, `library.pyi`, `__init__.pyi`
- **Type assertions**: Use proper type annotations after runtime checks
  ```python
  # BANNED: cast(dict[str, Any], data)
  # CORRECT: data_dict: IdentifierCollection = data
  ```

**Validation**: Type checker must report **zero errors**. Warnings about "partially unknown" types from JSON loading are acceptable since `json.load()` inherently returns `Any` and we validate at runtime with proper type narrowing.

**Rationale**: Strong typing prevents runtime errors, improves code clarity, enables better IDE support, and catches bugs at development time rather than production. JSON loading warnings are unavoidable but controlled through runtime validation.

---

## 21) Logging Policy (Full)

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

## 20) Contribution Rules

- Feature branches only; no versioned names (e.g., `processV2`). Delete superseded code.
- Small PRs with clear commit messages; add tests where behavior changes.
- Prefer explicit names; shallow control flow; no drive‑by abstractions.

---

## 21) Claude Interaction Rules (Operations Assistant)

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

## 22) Commit Messages (Conventional Commits 1.0.0)

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

## 23) Feature Implementation & Safety (Detailed)

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

## 24) Incident Response (Detailed)

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

**Prevention**

- Review and improve monitoring/alerting on CI and data integrity checks.
- Consider automated backups or snapshots before critical operations.
- Enhance documentation and training on the importance of the triple-file integrity and backup procedures.

---

## 25) Production Data Protection (Detailed)

### **CRITICAL RULE: NEVER Test/Debug with Production Data**

**The Problem: Data Corruption Risk**

Testing or debugging code directly on production data files (`bib/library.bib`, `data/identifier_collection.json`, `data/add_order.json`) creates catastrophic risk:

- **Silent bugs** can corrupt years of bibliographic work
- **Type errors** may cause encoding issues or data loss
- **API misuse** can result in empty files or malformed entries
- **Interrupted operations** can leave files in inconsistent states
- **No recovery** if backup protocol is skipped during development

### **Mandatory Testing Protocol**

**Rule 1: Use Sample/Test Data Only**

```powershell
# ✅ CORRECT - Copy production data for testing
cp bib/library.bib tests/fixtures/sample_library.bib
cp data/identifier_collection.json tests/fixtures/sample_identifiers.json
cp data/add_order.json tests/fixtures/sample_add_order.json

# Then work with copies
uv run python -c "
from pathlib import Path
from biblib.sync import sync_identifiers_to_library
sync_identifiers_to_library(Path('tests/fixtures'))
"

# ❌ WRONG - Working directly on production
uv run python -c "
from pathlib import Path
from biblib.sync import sync_identifiers_to_library
sync_identifiers_to_library(Path('.'))  # Modifies real data!
"
```

**Rule 2: Use Temporary Directories for Development**

```python
# ✅ CORRECT - Isolated test environment
import tempfile
from pathlib import Path

def test_new_feature():
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)

        # Copy sample data
        (workspace / "bib").mkdir()
        (workspace / "data").mkdir()

        # Work with copies only
        sample_lib = workspace / "bib" / "library.bib"
        sample_lib.write_text(SAMPLE_BIB_CONTENT)

        # Test your feature here safely
        result = my_function(workspace)

        # Validate results
        assert result.success

# ❌ WRONG - Testing on production files directly
def test_new_feature_wrong():
    result = my_function(Path("."))  # Operates on real files!
```

**Rule 3: Sample Data Creation Guidelines**

When you need realistic data for testing:

```python
# ✅ Create minimal samples that represent real patterns
SAMPLE_BIB_CONTENT = '''
@article{sample2024test,
  author = {Smith, John and Doe, Jane},
  title = {Sample Article for Testing},
  journal = {Test Journal},
  year = {2024},
  doi = {10.1000/test.sample},
}

@book{example2023book,
  author = {Brown, Alice},
  title = {Example Book Title},
  publisher = {Academic Press},
  year = {2023},
  isbn = {978-0123456789},
}
'''

SAMPLE_IDENTIFIERS = {
    "sample2024test": {
        "identifiers": {
            "doi": "10.1000/test.sample",
            "title": "Sample Article for Testing"
        }
    },
    "example2023book": {
        "identifiers": {
            "isbn": "978-0123456789",
            "title": "Example Book Title"
        }
    }
}
```

### **Development Workflow Requirements**

1. **Always Use Fixtures**: Create `tests/fixtures/` with sample data
2. **Copy, Don't Link**: Make actual copies, not symlinks to production data
3. **Temporary Workspaces**: Use `tempfile.TemporaryDirectory()` for isolated testing
4. **Validate Copies**: Ensure test data represents real patterns without being production data
5. **Document Test Data**: Comment what each fixture represents and why

### **Emergency Recovery Protocol**

If production data is accidentally modified:

```powershell
# 1. STOP immediately - don't make it worse
# 2. Check if backup exists
ls backups/

# 3. Restore from most recent backup
cp "backups/backup-YYYY-MM-DD-HHMMSS/bib/library.bib" bib/
cp "backups/backup-YYYY-MM-DD-HHMMSS/data/identifier_collection.json" data/
cp "backups/backup-YYYY-MM-DD-HHMMSS/data/add_order.json" data/

# 4. Validate restoration
uv run blx validate

# 5. Document incident in CLAUDE.md Section 15
```

### **Code Review Checklist**

For any code that handles data files:

- [ ] **Uses test data only**: No paths pointing to `bib/`, `data/` directories
- [ ] **Temporary workspace**: Uses `tempfile` or `tests/fixtures/`
- [ ] **Sample data provided**: Realistic but minimal test fixtures included
- [ ] **No production paths**: No hardcoded references to real data files
- [ ] **Backup compliance**: Any production operations include mandatory backup

**Remember: Your bibliography is irreplaceable. Test data is replaceable. Always choose safety.**

---

## 26) Preventing API Misuse Bugs (Detailed)

### **The Problem: Silent API Failures**

Modern libraries often have multiple ways to do the same thing, and not all methods work as expected. The bibtexparser v2 incident (library.entries.append() vs library.add()) exemplifies this - the wrong method silently failed without errors.

### **Mandatory API Validation Checklist**

Before using any external library method:

1. **Consult Official Documentation First**
   ```powershell
   # For Python libraries, always check help() in REPL
   python -c "import bibtexparser; help(bibtexparser.Library.add)"
   # or dir() to explore available methods
   python -c "import bibtexparser; print([m for m in dir(bibtexparser.Library()) if not m.startswith('_')])"
   ```

2. **Write Minimal Test Cases**
   - Create isolated test with expected vs actual output
   - Verify the operation actually works before integrating
   ```python
   # Example validation test
   lib = bibtexparser.Library()
   entry = parsed_entry  # from known working parse

   # Test approach 1
   lib.entries.append(entry)
   assert len(lib.entries) > 0, "append() failed silently"

   # Test approach 2
   lib.add(entry)
   assert len(lib.entries) > 0, "add() failed silently"
   ```

3. **Check Version-Specific Behavior**
   - Major version changes often break APIs
   - bibtexparser v1 vs v2 have different Entry construction
   - Always specify exact version in dependencies
   ```toml
   # pyproject.toml - be specific about versions
   dependencies = [
       "bibtexparser>=2.0.0,<3.0.0"  # Pin major version
   ]
   ```

### **Integration Test Requirements**

**Rule:** All file I/O operations MUST have integration tests that verify actual file contents.

```python
# ❌ BAD - mocked test that hides real bugs
@patch('biblib.add_entries.append_to_files')
def test_add_entries(mock_append):
    mock_append.return_value = True  # Lies about success
    result = add_entries_from_staging(workspace)
    assert result  # Passes but real function is broken

# ✅ GOOD - real test that catches file I/O bugs
def test_add_entries_real_files():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Test with actual files
        result = add_entries_from_staging(workspace)

        # Verify actual file contents
        bib_content = Path(tmpdir).joinpath("library.bib").read_text()
        assert "@article{" in bib_content  # Real verification
```

### **Documentation Verification Protocol**

When implementing features with external libraries:

1. **API Reference Check**
   - Read official docs for the specific version
   - Check GitHub issues for known problems
   - Look for migration guides between versions

2. **Working Example Validation**
   - Find official examples that work
   - Copy and modify incrementally
   - Never assume similar-looking methods work the same

3. **Error Handling Verification**
   - Test what happens when operations fail
   - Ensure failures are detected, not silently ignored
   ```python
   # Verify operations actually work
   before_count = len(library.entries)
   library.add(entry)
   after_count = len(library.entries)
   if after_count == before_count:
       raise RuntimeError("Entry was not added to library")
   ```

### **Mandatory Code Review Points**

For all external library usage:

- [ ] **Method source verified**: Official docs consulted for this exact method
- [ ] **Return value validated**: Operation success confirmed by checking results
- [ ] **Integration tested**: Real file I/O tested, not just mocked
- [ ] **Error handling**: Failures detected and reported properly
- [ ] **Version pinned**: Exact version specified to prevent surprise updates

### **Library-Specific Guidelines**

**bibtexparser v2:**
```python
# ✅ CORRECT patterns
library = bibtexparser.parse_file(str(path))        # File parsing
library.add(entry)                                  # Adding entries
bib_string = bibtexparser.write_string(library)     # Serialization

# ❌ WRONG patterns (silent failures)
library.entries.append(entry)                       # Doesn't work
bibtexparser.write_file(path, library)             # May use wrong encoding
```

**JSON handling:**
```python
# ✅ CORRECT with UTF-8 explicit
with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

# ❌ WRONG - system default encoding
with open(path, "w") as f:  # May use CP950 on Windows
    json.dump(data, f)
```

### **Prevention Summary**

1. **Never assume**: Test every external library method before using
2. **Document explicitly**: Write down which methods work and which don't
3. **Integration test**: Always verify real file operations work
4. **Pin versions**: Prevent surprise API changes from updates
5. **Validate results**: Check that operations actually succeeded

---

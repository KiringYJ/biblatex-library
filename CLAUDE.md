# CLAUDE.md — Project Operating Guide (biblatex-library)

> Project-specific rules and context. General engineering rules live in `.claude/rules/`.

---

## 1) Philosophy & Pointers

**Collaboration contract**

1. We ship production-grade bibliography tooling; correctness > speed.
2. Process for every change: **Research -> Plan -> Implement -> Validate**.
3. All code must be: **explicit**, **small**, **reversible**, **test-anchored**.

**Core behavioral rules**
- Default stance: *skeptical until proven necessary.*
- Simplicity beats flexibility. Remove special cases by fixing invariants.
- Never break userspace (existing workflows, file formats, CLI flags).
- Data safety is not optional — backups and isolation precede mutation.

**Detailed rules** (read these files for full policies):
- `.claude/rules/review.md` — Linus Mode review criteria, NACK triggers, accept criteria
- `.claude/rules/workflow.md` — Test-first workflow, pre-commit checklist, quality gates
- `.claude/rules/interaction.md` — Plan-first rule, bash usage, do/don't
- `.claude/rules/output.md` — Logging policy (no `print` for diagnostics)
- `.claude/rules/naming.md` — File & directory naming conventions

**Skills** (invoke with `/skill-name`):
- `/commit` — Pre-commit checks + conventional commit
- `/review` — Linus Mode code review
- `/pre-push` — Tests + validation before push
- `/optimize` — Profiling workflow

---

## 2) Critical Data Integrity & Safety

### 2.1 Triple-File Consistency (Citekey Integrity)
The following three files form an atomic consistency set:
1. `bib/library.bib`
2. `data/identifier_collection.json`
3. `data/add_order.json`

Any add/remove/rename/reorder of citekeys MUST update all three. Validation (`uv run blx validate`) is a merge blocker if inconsistent.

### 2.2 Backup Protocol (Mandatory Before Mutation)
Prior to any modification of the triple set:

```powershell
$ts = Get-Date -Format 'yyyyMMdd-HHmmss'
$backup = "staging/backup-$ts"
New-Item -ItemType Directory -Path $backup | Out-Null
Copy-Item bib/library.bib $backup/
Copy-Item data/identifier_collection.json $backup/
Copy-Item data/add_order.json $backup/
```

**Automatic cleanup**: Post-commit hook removes all staging backup directories since git provides full version history.

### 2.3 Production Data Protection
**NEVER test or debug on production data.** Copy or sample — never operate in-place. Use fixtures or `tempfile.TemporaryDirectory()`.

### 2.4 Encoding Invariant
All file I/O uses `encoding="utf-8"` with `ensure_ascii=False` for JSON. Failure to specify encoding = defect. See Section 8 for rationale.

### 2.5 Mutation Preconditions
- Tests green (new + existing)
- `ruff check --fix` -> `ruff format` -> `ty` = clean
- Backup timestamp < 5 minutes
- Dry run (if available) reviewed

---

## 3) Incident Response
1. STOP — no speculative edits.
2. Inspect recent diffs (`git log -p`).
3. Reproduce on `main`.
4. Restore from backup if corruption present.
5. Re-validate: `uv run blx validate`.
6. Add post-mortem note if systemic.
7. Strengthen guardrails (tests/validation) before closing.

---

## 4) Repository Overview

This repo maintains a curated **biblatex** library and tooling to:

- Validate/normalize/sort the `.bib` database
- Generate **CSL-JSON** and convert to **BibTeX**
- Provide **biblatex** and **amsrefs** LaTeX examples
- Host our custom biblatex style (`yj-standard`)

### Repository Layout

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
│  ├─ mappings/{types,fields}.yml # declarative maps biblatex<->CSL
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
├─ .claude/                       # Claude Code configuration
│  ├─ rules/                      # engineering rules
│  ├─ skills/                     # invocable skills
│  ├─ scripts/                    # hooks scripts
│  ├─ settings.json               # plugin config
│  └─ hooks.json                  # prompt/tool hooks
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

---

## 5) Data Model (Biblatex vs BibTeX)

**Biblatex data model note**
- `bib/library.bib` is written for **biblatex** (not classic BibTeX). It may use biblatex-only entry types such as `@online` and `@thesis`.
- Classic BibTeX does **not** define these types, so **conversion/mapping is required** for BibTeX/amsrefs workflows.
- Our converter maps `@thesis` -> `@phdthesis`/`@mastersthesis` (based on `type` field) and `@online` -> `@misc` (carrying `url`/`urldate`).

**Three-file synchronization requirement**

When working with citekeys/labels, **ALWAYS** update these three files simultaneously:
1. `bib/library.bib` — Bibliographic entries with `@type{citekey, ...}`
2. `data/identifier_collection.json` — Identifier mappings with citekey as top-level keys
3. `data/add_order.json` — Entry order array containing citekeys

**Required operations for citekey changes**
- **Adding**: Add to all three files
- **Removing**: Remove from all three files
- **Renaming**: Update in all three files (use `blx validate --fix` for automated fixing)
- **Reordering**: Update `library.bib` and `identifier_collection.json`

**Automation**: `blx validate --fix` auto-fixes citekey mismatches. Any inconsistency is a hard merge blocker.

---

## 6) Build & Run Quickstart

### Python (Windows PowerShell)

```powershell
# Python 3.13 with UV package manager
uv sync --dev
uv run python -m pytest
uv run blx validate
```

### LaTeX examples

```powershell
cd latex/examples/alphabetic
latexmk -pdf -xelatex main.tex
```

### VS Code (LaTeX Workshop)

Preferred recipe: `latexmk (XeLaTeX+biber)` for biblatex demos.

---

## 7) The `blx` CLI

```powershell
uv run blx validate                # JSON Schema + biber --tool checks
uv run blx add                     # process staging directory entries
uv run blx template                # generate identifier JSON templates from staging .bib
uv run blx sort alphabetical       # sort by citekey
uv run blx sort add-order          # sort to match add_order.json sequence
uv run blx generate-labels         # generate labels for biblatex entries
uv run blx normalize latex-accents # normalize LaTeX accent commands
uv run blx normalize year-to-date  # normalize year fields to date
uv run blx normalize eprint-fields # normalize eprint fields
```

---

## 8) UTF-8 & Encoding Policy

**The Problem**: On Chinese Windows, `bibtexparser.write_file()` uses system default CP950 encoding, which cannot represent characters like **学** (`\u5b66`). This caused `'cp950' codec can't encode character` errors.

**Hard rules**:
- **ALL** file I/O MUST specify `encoding="utf-8"` — no exceptions.
- Use `bibtexparser.write_string()` then write with explicit encoding (not `write_file()`).
- JSON: `json.dump(data, f, ensure_ascii=False, indent=2)` with `encoding="utf-8"`.

```python
# bibtexparser: serialize to string, then write with encoding
bibtex_string = btp.write_string(library)
with open(bib_path, "w", encoding="utf-8") as f:
    f.write(bibtex_string)
```

---

## 9) .bib Parsing & Writing Policy (bibtexparser v2)

- **Never** hand-parse `.bib` (no regex/tokenizers). Use **bibtexparser v2** for all operations.
- Check `lib.failed_blocks` and fail CI if non-empty.
- Use **latexcodec/pylatexenc** for LaTeX<->Unicode conversion when exporting.

**Known API gotchas** (bibtexparser v2):

```python
# CORRECT
library.add(entry)                              # Adding entries
bib_string = bibtexparser.write_string(library)  # Serialization

# WRONG (silent failures)
library.entries.append(entry)                    # Does NOT work
bibtexparser.write_file(path, library)          # Wrong encoding on Windows
```

Always verify external library operations succeed (check length/contents after mutation). Pin versions in `pyproject.toml`.

---

## 10) Add Order Ledger

- Canonical order lives in `data/add_order.json` (**append-only**); top-level key `order` is an array of entry keys.
- `blx order add KEY ...` — append to ledger
- `blx order check` — verify existence/duplicates

---

## 11) Custom biblatex Style: `biblatex-yj`

- **Style id**: `yj` (and variants like `yj-trad-alpha`).
- Load with `\usepackage[style=yj]{biblatex}` or `\usepackage{biblatex-yj}`.
- Use **l3build** for regression tests; keep minimal examples in `tex/biblatex-yj/examples/`.

---

## 12) LaTeX Examples

- `latex/examples/biblatex-spbasic/` — `style=biblatex-spbasic`
- `latex/examples/alphabetic/` — `style=alphabetic`

---

## 13) Type Safety Policy

**Zero-tolerance**: `Any` and `type: ignore` are **BANNED**.

- **JSON data**: Use TypedDict definitions from `src/biblib/types.py` (`IdentifierCollection`, `AddOrderList`, `IdentifierData`)
- **External libraries**: Create type stubs in `typings/` (e.g., `typings/bibtexparser/`)
- **No `cast()` with weak types** — use proper type annotations after runtime checks
- Type checker must report **zero errors**. Warnings about "partially unknown" from `json.load()` are acceptable.

---

## 14) Commit Messages (Conventional Commits 1.0.0)

```
<type>(<optional scope>)<optional !>: <subject>
```

**Types**: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`

**Scopes**: `cli`, `convert`, `csl`, `style`, `tex`, `examples`, `data`, `ledger`, `ci`, `docs`

**Examples**:
```
feat(cli): add `blx csl gen` to export CSL-JSON
fix(style): correct `yj-standard.cbx` date formatting
refactor(convert): unify biblatex->BibTeX mapping pipeline
```

# TODO

> **Done** = implementation merged, **Verified** = manually tested / snapshot-covered.

## Planned Features

| Done | Verified | Item |
|:----:|:--------:|------|
| [ ]  | [ ]      | Biblatex to BibTeX conversion |
| [ ]  | [ ]      | CSL-JSON export |
| [ ]  | [ ]      | API enrichment (CrossRef, arXiv) |
| [ ]  | [ ]      | Duplicate detection |
| [ ]  | [ ]      | Citation analysis |

---

### Biblatex to BibTeX conversion

**File:** `src/biblio/convert/` (empty, reserved)
- Convert `@online` -> `@misc`, `@thesis` -> `@phdthesis`/`@mastersthesis`
- Field conversion: `date` -> `year`/`month`, `journaltitle` -> `journal`, etc.
- Integration with `biber --tool` for robust processing
- CLI target: `biblio convert input.bib output.bib`

### CSL-JSON export

**File:** `csl/` (mostly empty, `schema/` dir reserved)
- Generate CSL-JSON from `library.bib` for Pandoc/Zotero compatibility
- Declarative type/field mappings planned (YAML)

### API enrichment (CrossRef, arXiv)

- Auto-fill missing metadata from CrossRef, arXiv, MathSciNet APIs
- `httpx` already in dependencies (`pyproject.toml`)

### Duplicate detection

- Find and merge duplicate entries based on identifiers (DOI, ISBN, etc.)

### Citation analysis

- Generate usage reports and statistics for the bibliography database

---

## Test Gaps

| Done | Verified | Item |
|:----:|:--------:|------|
| [ ]  | [ ]      | Template tests |

---

### Template tests

**File:** `tests/test_template.py` (does not exist)
- `biblio template` has no test coverage
- Needs tests for: template generation, overwrite behavior, identifier priority selection, edge cases

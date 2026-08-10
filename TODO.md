# Roadmap

`biblio` is a pure engine. New features belong under `src/biblio`, with tests
that use temporary consumer workspaces. Do not add production bibliography
data, TeX styles, or manuscript examples to this repository.

| Done | Verified | Item |
|:----:|:--------:|---|
| [ ] | [ ] | BibLaTeX-to-BibTeX conversion |
| [ ] | [ ] | CSL-JSON export |
| [ ] | [ ] | API enrichment |
| [ ] | [ ] | Duplicate detection |
| [ ] | [ ] | Citation analysis |

## BibLaTeX-to-BibTeX conversion

- Map BibLaTeX-only entry types such as `@online` and `@thesis` to classic
  BibTeX equivalents.
- Convert fields such as `date` and `journaltitle` without losing semantic
  information silently.
- Define a CLI contract with explicit input/output paths and regression
  fixtures before implementation.

## CSL-JSON export

- Export configured BibLaTeX data for Pandoc/Zotero-compatible consumers.
- Keep type and field mappings declarative and tested.
- Write output to a caller-selected path rather than a repository-owned data
  directory.

## API enrichment

- Enrich configured records from services such as Crossref and arXiv.
- Require explicit selection, deterministic merge rules, and dry-run output.
- Keep credentials and caches outside the engine repository.

## Duplicate detection

- Detect candidates using canonical identifiers before weaker metadata
  similarity.
- Report candidates separately from any destructive merge operation.

## Citation analysis

- Accept usage data or document manifests as explicit inputs.
- Produce machine-readable reports without coupling the engine to a manuscript
  repository or TeX build system.

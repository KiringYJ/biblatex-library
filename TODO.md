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

Retired standalone prototypes are historical reference material, not
compatibility contracts. Do not preserve their provider order, confidence
thresholds, in-place rewrites, or reduced field sets without fresh evidence.

## BibLaTeX-to-BibTeX conversion

- Map BibLaTeX-only entry types such as `@online` and `@thesis` to classic
  BibTeX equivalents.
- Convert fields such as `date` and `journaltitle` without losing semantic
  information silently.
- Define a CLI contract with explicit input/output paths and regression
  fixtures before implementation.

## CSL-JSON export

- Export the configured BibLaTeX workspace without performing network lookup.
- Map canonical citekeys to CSL `id` values and preserve workspace order with
  deterministic serialization.
- Keep type and field mappings declarative and tested. Report unsupported or
  lossy mappings explicitly rather than dropping data silently.
- Write output to a caller-selected path rather than a repository-owned data
  directory.
- Validate output against a declared CSL schema and representative consumer
  fixtures.
- Keep `library.bib` as the bibliographic source of truth until a separate,
  lossless CSL cutover is designed and verified.
- Preserve `identifier_collection.json` as the exact identity and citekey
  provenance bridge; a CSL record alone must not discard alternate,
  catalogue, or historical hash inputs.

## API enrichment

- Keep `audit` source-free; expose enrichment through a separate command and
  application service.
- Accept an explicit record or input set and return machine-readable candidates
  with provider and comparison evidence.
- Treat similarity as discovery evidence, not authority. Preserve ambiguous or
  conflicting candidates for review instead of selecting them automatically.
- Separate candidate discovery from application. Any mutation must require an
  explicit selection, support dry-run, and use the existing transaction and
  recovery boundaries.
- Treat provider choice and fallback order as implementation details rather
  than compatibility guarantees.
- Keep credentials and caches outside the engine repository; cached responses
  are not a source of truth.
- Use fixtures or mocked responses in tests so the normal suite remains
  network-free.

## Duplicate detection

- Detect candidates using canonical identifiers before weaker metadata
  similarity.
- Report candidates separately from any destructive merge operation.

## Citation analysis

- Accept usage data or document manifests as explicit inputs.
- Produce machine-readable reports without coupling the engine to a manuscript
  repository or TeX build system.

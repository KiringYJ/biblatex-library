# Project-Specific Agent Context

This file contains the project-specific rules for `biblatex-library`. The
generated `AI_AGENT_GUIDE.md` supplies the shared engineering policy.

## Purpose and boundary

This repository is a pure Python engine named `biblio`. It owns the CLI,
BibLaTeX parsing and normalization, identifier provenance, citekey generation,
three-artifact validation and recovery, tests, schemas, and type stubs.

It does not own production bibliography data, staging inputs, TeX styles,
classes, manuscripts, or publication builds. The principal consumer is
`KiringYJ/tex-studies`, maintained in a separate checkout. Treat that repository
as read-only unless the user explicitly places it in scope.

The engine repository must not track consumer `bib/`, `data/`, `staging/`,
`latex/`, or `tex/` trees. The wheel target is only `src/biblio`.

## Workspace model

A consumer workspace is one coordinated integrity set with bounded ownership:

1. `library.bib` owns active bibliographic/rendering metadata, canonical
   citekeys, BibLaTeX `ids` aliases, and physical record order.
2. `identifier_collection.json` owns the complete exact identifier inventory
   and citekey-hash provenance. JSON-only identifiers are valid. Optional
   `identifier_alternates` and `key_history` extend the existing flat format
   without invalidating legacy records.
3. `add_order.json` owns the chronological sequence of active canonical keys.
   It must equal physical `.bib` order exactly.

CSL may replace BibLaTeX as the bibliographic metadata layer in the future,
but exact identifier provenance and chronological order must remain lossless.

`biblio.toml` defines all four consumer paths relative to the config file:

```toml
[paths]
bib = "bib/library.bib"
identifiers = "data/identifier_collection.json"
add_order = "data/add_order.json"
staging = "staging"
```

`biblio init <target>` creates this layout without overwriting existing data.

## Architecture

```text
src/biblio/
  cli.py                    thin argument and rendering adapter
  commands.py               one application service per CLI operation
  bibliography.py           ordered BibLaTeX aggregate and alias index
  identifier_collection.py  exact identifier and order-ledger models/codecs
  workspace.py              cross-artifact invariants
  storage.py                codecs, locks, transactions, and recovery
  lifecycle.py              pure add/remove/promotion transforms
  add_entries.py            arbitrary .bib staging intake and key preparation
  normalize/                pure in-memory normalization passes
  validate.py               BibLaTeX semantic validation
  schema/                   current identifier collection schema
tests/                       temporary-workspace and integration regressions
typings/                     precise external-package stubs
```

Normal commands load one workspace aggregate and request at most one
three-artifact commit. Standalone `sort`, `sync`, `template`,
`generate-labels`, and migration-away commands are retired.

## Invariants

- Canonical keysets are identical across all three artifacts.
- `.bib` physical order equals `add_order.json` exactly.
- Canonical keys plus all `ids` aliases are globally injective.
- Every canonical or historical key suffix hashes the exact UTF-8 identifier
  value recorded in JSON; comparison normalization never rewrites that value.
- Every identifier projected into `.bib` has a kind-equivalent JSON value.
  Additional JSON-only identifiers are preserved.
- Promotion makes the publisher DOI key canonical, retains prior keys as
  direct aliases with complete `key_history`, and preserves the order slot.
- Hard removal deletes the active record from all three artifacts. Consumer
  version control, not a live tombstone, retains intentional deletion history.
- Add appends. Normal commands never alphabetically reorder records.

## Data safety

- Never test or debug against consumer production data. Use pytest fixtures or
  `tempfile.TemporaryDirectory()`.
- Do not modify the principal consumer checkout while changing this engine.
- The engine is Git-independent and must not create timestamped backups.
- Mutation uses the recoverable workspace transaction. Transaction-only
  candidate and rollback shadows are crash evidence, not user history.
- Never bypass unresolved recovery state or overwrite a third-party digest.
- `validate` is side-effect-free; mutation and recovery use deterministic
  multi-file locking.
- Staging filenames are arbitrary. Directory intake is nonrecursive and
  accepts regular `*.bib` files only. Consume inputs only after a verified
  workspace commit, using digest-bound cleanup receipts; dry-run and failure
  preserve inputs.
- All text I/O is UTF-8. JSON serialization uses `ensure_ascii=False`.
- Use `bibtexparser` v2 for parsing/serialization and check failed blocks.

`pre-commit-data-hooks.yaml` is an optional consumer template for the default
paths, not this repository's own hook configuration.

## Development workflow

Use Python 3.13 and UV:

```powershell
uv sync --dev
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv build
```

Add the narrowest regression before behavior changes. Tests must use fixtures,
not live consumer data. The explicitly marked biber alias test may require the
local TeX toolchain; ordinary tests must not require network access.

## Type safety

- `Any` and `type: ignore` are prohibited.
- Prefer typed dataclasses and precise collection types at JSON boundaries.
- Add precise stubs under `typings/` when dependencies lack annotations.
- `uv run ty check` must report zero errors and warnings.

## Public CLI

Current commands are:

```text
biblio init
biblio validate
biblio add [STAGING] [--dry-run]
biblio normalize [ACTION] [--dry-run]
biblio remove KEY [--dry-run]
biblio promote KEY PUBLISHED.bib [--dry-run]
biblio recover [--status|--dry-run]
```

Current normalization actions are `year-to-date`, `publisher-location`,
`eprint-fields`, `latex-accents`, `isbn`, and `trivial-url`.

Preferred Conventional Commit scopes are `domain`, `storage`, `cli`, `config`,
`normalize`, `validate`, `lifecycle`, `init`, `schema`, `tests`, `tooling`, and
`docs`.

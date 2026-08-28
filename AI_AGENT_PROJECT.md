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
  audit.py                  deterministic source-free compliance findings
  normalize/                pure in-memory normalization passes
  validate.py               BibLaTeX semantic validation
  schema/                   current identifier collection schema
tests/                       temporary-workspace and integration regressions
typings/                     precise external-package stubs
```

Normal commands load one workspace aggregate and request at most one
three-artifact commit. Standalone `sort`, `sync`, `generate-labels`, and
migration-away commands are retired.

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
- `validate` and `audit` are side-effect-free; mutation and recovery use deterministic
  multi-file locking.
- Staging filenames are arbitrary. Directory intake is nonrecursive and
  selects regular `*.bib` files. `template` writes a same-stem JSON companion
  with one independently reviewable identifier record per temporary entry key;
  `add` honors a present companion and otherwise uses deterministic defaults.
  Consume bibliography and companion inputs only after a verified workspace
  commit, using digest-bound cleanup receipts; dry-run and failure preserve
  inputs.
- `add` runs all supported normalization actions against incoming entries
  before canonical key derivation, leaves existing entries untouched, and
  validates the complete normalized workspace candidate before committing.
- Normalization must not infer bibliographic roles or rewrite unparsed TeX/name
  syntax. Match field names case-insensitively and reject duplicates before
  mutation. Preserve unsupported values and conflicting aliases for review.
- The explicit arXiv import convention converts only `@misc` with arXiv
  `eprinttype` (or `archiveprefix`) and a nonempty `eprint` to `@online`.
  Preserve all other entry types and the exact identifier. Conflicting aliases
  block the entire eprint transformation; duplicate eprint fields fail before
  mutation. Do not remove this accepted convention as generic type inference.
- Both journal-field and book-pagination migration require a nonempty
  `mrnumber`, `mrclass`, or `mrreviewer` field in the entry, using the shared
  `normalize/mr.py` predicate. Do not infer this from similar names, URLs,
  citekeys, the journal pair alone, or JSON-only metadata. This is the accepted
  local import convention, not proof of export provenance.
- On marked records, a nonempty `journal` + `fjournal` pair means abbreviated
  and full journal names respectively. Migrate the pair atomically to
  `shortjournal` + `journaltitle`, preserving exact values and both sources on
  any target conflict. Lone legacy fields remain review-only.
- Book-pagination migration additionally requires `@book`, no `chapter`,
  absent or `page` pagination units, and a supported positive count or canonical
  Roman-plus-Arabic extent. Preserve the exact extent string; do not sum parts
  or reinterpret ranges. A differing `pagetotal` blocks the change.
- Name/TeX normalization uses a bounded source-preserving grammar. Retain groups,
  quoted/literal names, and opaque identifiers; leave unsupported contexts
  unchanged. Do not use macro-prefix replacement or generic brace stripping.
- ISBN normalization validates the entire bare identifier list before mutation,
  converts ISBN-10 to contiguous ISBN-13 digits, and does not infer hyphenation.
  Existing exact identifier provenance and reviewed companion selections remain
  authoritative; do not change legacy identifier-comparison rules as a cleanup.
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
biblio audit
biblio template [STAGING] [--overwrite]
biblio add [STAGING] [--dry-run]
biblio normalize [ACTION] [--dry-run]
biblio remove KEY [--dry-run]
biblio promote KEY PUBLISHED.bib [--dry-run]
biblio recover [--status|--dry-run]
```

Current normalization actions are `year-to-date`, `eprint-fields`,
`latex-accents`, `name-spacing`, `journal-fields`, `book-pagination`, `isbn`, and
`trivial-url`, in that order. Text representation changes precede MR-pair comparison to keep
`all` idempotent. The pipeline registry also supplies CLI choices through the
commands service. Year conversion requires a bare ASCII four-digit year with
no date/month; eprint aliases must not override conflicts, and only the explicit
arXiv `@misc` import convention may change the entry type;
URL removal requires an exact identifier-derived link, not URL equivalence.

`publisher-location` is retired and rejected. Audit may offer MR-pair,
MR-book-extent, and name-spacing fixes only when the corresponding normalizer
preconditions pass. Unmarked, scoped, or ambiguous inputs remain review-only.

Preferred Conventional Commit scopes are `domain`, `storage`, `cli`, `config`,
`normalize`, `validate`, `lifecycle`, `init`, `schema`, `tests`, `tooling`, and
`docs`.

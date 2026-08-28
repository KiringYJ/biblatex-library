# biblio

`biblio` is a Python 3.13 command-line engine for maintaining a coordinated
BibLaTeX workspace. It validates and changes three consumer-owned artifacts as
one integrity set:

- `library.bib` is the authority for active bibliographic metadata, BibLaTeX
  rendering fields, canonical citekeys, and `ids` aliases consumed by biber.
- `identifier_collection.json` is the authority for the exact, complete
  identifier inventory and the identifier values used to derive citekey
  hashes. Optional `identifier_alternates` and `key_history` retain promotion
  provenance while remaining backward compatible with records containing
  only `main_identifier` and `identifiers`.
- `add_order.json` is the authority for the chronological order of active
  records. Its order must equal physical entry order in `library.bib`.

This repository contains only the engine, tests, schemas, and type stubs. It
does not contain or modify a production bibliography, staging inbox,
manuscript, TeX style, or publication build.

BibLaTeX is the current bibliographic interchange and rendering format. A
future CSL-backed design could replace the bibliographic-metadata layer, but
it would still need to preserve exact identifier provenance, citekey history,
and chronological ordering.

The current engine recognizes eleven identifier kinds: `doi`, `isbn13`,
`arxiv`, `url`, `mrnumber`, `zbl`, `zbmath`, `jfm`, `oclc`, `hdl`, and
`acmdl_doi`. The JSON codec and schema preserve an unknown kind so future data
is not discarded, but workspace validation reports it as unsupported and
mutation commands fail closed until the engine gains an explicit comparison
and projection rule for that kind. JSON-only values of the eleven supported
kinds are valid and remain part of the complete inventory.

## Principal consumer

The principal consumer is
[`KiringYJ/tex-studies`](https://github.com/KiringYJ/tex-studies). That
repository owns its live bibliography, BibLaTeX styles, biber and LuaLaTeX
builds, and publication exports. It is referenced here as a read-only consumer
example; this engine repository does not edit or migrate it.

Its exact four-path configuration is:

```toml
[paths]
bib = "shared/bibtex/bib/library.bib"
identifiers = "shared/data/identifier_collection.json"
add_order = "shared/data/add_order.json"
staging = "shared/bibtex/bib/staging"
```

Paths are resolved relative to `biblio.toml`.

## Installation

```powershell
git clone https://github.com/KiringYJ/biblatex-library.git
Set-Location biblatex-library
uv sync --dev
uv run biblio --help
```

A consumer can install a pinned Git revision:

```toml
[project]
dependencies = [
  "biblio @ git+https://github.com/KiringYJ/biblatex-library",
]
```

## Initialize a workspace

```powershell
biblio init D:\path\to\bibliography-workspace
```

This creates:

```text
biblio.toml
bib/library.bib
data/identifier_collection.json
data/add_order.json
staging/
```

The default config is:

```toml
[paths]
bib = "bib/library.bib"
identifiers = "data/identifier_collection.json"
add_order = "data/add_order.json"
staging = "staging"
```

Existing data files are never overwritten. `biblio init --force` permits
replacing an existing `biblio.toml`, not consumer bibliography data.

## CLI

Global path options must precede the command:

```text
--config PATH       Use an explicit biblio.toml
--bib PATH          Override library.bib
--identifiers PATH  Override identifier_collection.json
--add-order PATH    Override add_order.json
--staging PATH      Override the staging directory
-v / -vv            Increase diagnostic verbosity
```

Commands print concise human-readable summaries by default. Pass `--json`
before or after the command to print the complete machine-readable result:

```powershell
biblio add --json
biblio --json validate
biblio normalize --dry-run --json
```

Scripts that previously parsed the default JSON output must now request
`--json`; its payload format is unchanged. Warnings and errors remain on
standard error in both modes, and exit codes are unchanged. `-v` and `-vv`
only change logging verbosity, not the result format.

From the root of a configured consumer checkout, a read-only validation
invocation is:

```powershell
biblio --config .\biblio.toml validate
```

### Upgrade a legacy identifier inventory

Legacy workspaces may contain supported identifiers in `library.bib` that are
missing from `identifier_collection.json`. Reconcile those one way before the
first validation:

```powershell
biblio reconcile --dry-run
biblio reconcile
biblio validate
```

This upgrade does not edit a consumer automatically. Run it only inside the
consumer workspace selected by its config or explicit path overrides.

### Validate

```powershell
biblio validate
```

Validation reads a stable three-file snapshot and checks:

- equal canonical key sets across all artifacts;
- physical `.bib` order equal to `add_order.json`;
- exact main-identifier hash provenance;
- identifier inventory completeness and global uniqueness;
- BibLaTeX aliases equal the optional `key_history` projection; and
- absence of unresolved workspace recovery state.

### Audit deterministic bibliography conventions

```powershell
biblio audit
```

`audit` is read-only and uses only the parsed bibliography. It does not query
publishers, catalogues, identifier registries, or the network. A finding supplies
`fix_action` only when the corresponding normalizer can apply its stated input
contract. Other observations remain review-only: detecting a suspicious value
does not establish a meaning-preserving replacement.

The audit currently detects:

- MR-marked `journal`/`fjournal` pairs, unmarked/incomplete pairs, and conflicting
  destination values; lone `journal` values retain the standard alias check;
- nonstandard `eissn`, comma-packed `issn`, and invalid ISSN check digits;
- marked MR book extents, conflicting totals, and unmarked or scoped `pages`
  values that remain review-only;
- four confirmed invalid field/type pairs on `@online` and `@unpublished`;
- year-like `edition` values and whitespace before commas in name fields;
- multiple explicit `journaltitle` or `shortjournal` values attached to one
  exact ISSN, without assigning roles to legacy fields; and
- series values that differ only by letter case.

Findings describe observable patterns, not necessarily bibliographic errors.
The engine cannot choose, for example, a print versus electronic ISSN or an
authoritative journal spelling without source evidence.

### Generate reviewable staging templates

```powershell
biblio template
biblio template D:\temporary\batch.bib
biblio template --overwrite
```

`template` writes one editable `.json` companion beside each selected `.bib`
file. A single `.bib` may contain many entries; the companion contains one
independent `main_identifier` and complete identifier inventory per temporary
entry key. Review or change those selections before `add`. JSON-only supported
identifiers may be added to the companion without placing non-rendering data in
BibLaTeX fields.

Template generation applies the same deterministic DOI canonicalization and
in-memory normalization used by `add`, so the displayed identifier values and
default selections match the eventual candidate. Existing companions are
preserved unless `--overwrite` is explicit.

The default priority is `doi`, `isbn13`, `mrnumber`, `arxiv`, `zbmath`, `zbl`,
`jfm`, `oclc`, `hdl`, `acmdl_doi`, then `url`. When a DOI is only the matching
arXiv-issued `10.48550/arXiv...` form, the arXiv eprint remains the default main
identifier. The redundant DOI and exact derived links are omitted from both
the normalized BibLaTeX and generated identifier JSON. A distinct publisher
DOI retains normal DOI priority.

### Add and consume staging files

```powershell
biblio add --dry-run
biblio add
biblio add D:\temporary\one-record.bib --dry-run
```

A verified import prints the added-entry count and only the new citekeys:

```text
Added 1 entry.
  doe-2024-01234567
```

Dry runs are labeled as previews; failed or unverified commits and incomplete
cleanup are reported separately. Use `biblio add --dry-run --json` to review
the complete normalization changes and before/after order. Plain output omits
those internal details and per-artifact hashes.

Staging filenames are arbitrary temporary names and do not need dates or
slugs. Directory intake is nonrecursive and processes regular `.bib` files in
deterministic filename order. A positional `STAGING` value may identify one
`.bib` file or another inbox directory. When a same-stem `.json` companion is
present, `add` validates and honors every reviewed per-entry selection; without
one, it uses the documented deterministic identifier priority.

`add` applies every supported normalization action to the incoming entries
before deriving citekeys and identifier records. It does not normalize existing
library entries as a side effect of an import. The command validates the current
workspace before intake and the complete normalized three-artifact candidate
before any write, so a successful `add` does not require a separate `normalize`
or `validate` command.

The normalized entries, exact identifier records, and chronological order are
installed in one coordinated transaction. Before committing, `add` durably
records a cleanup receipt bound to the exact `.bib` and companion bytes,
generated keys, and original and candidate workspace digests. Staging files
and companions are deleted only after the three-artifact commit is verified.
They remain untouched after dry-run, normalization or validation failure,
write failure, or an unverified commit.

If verified content commits but file deletion cannot finish, the reduced
cleanup receipt remains and the command exits nonzero. Rerun the same
`biblio add` command to resume digest- and key-checked cleanup. A changed file
is retained and reported as a conflict; it is never deleted on the basis of a
stale or fabricated receipt.

### Normalize

```powershell
biblio normalize --dry-run
biblio normalize trivial-url
biblio normalize arxiv-doi
```

The default action is `all`. Only bounded representation changes are automatic:

| Action | Supported transformation |
| --- | --- |
| `year-to-date` | Rename an exact four-digit ASCII `year` when neither `date` nor `month` is present. Other year values remain for review. |
| `eprint-fields` | Migrate the documented `archiveprefix`/`primaryclass` aliases and canonicalize the arXiv marker. Restore the arXiv import convention: `@misc` with an explicit arXiv type and nonempty `eprint` becomes `@online`. Preserve other entry types and conflicting metadata. |
| `latex-accents` | Convert complete supported accent and letter commands in text/name fields, preserving groups and unrelated text. In `mrreviewer` only, convert supported control-space tokens to ordinary spaces. Leave opaque identifiers and unsupported TeX contexts unchanged. |
| `name-spacing` | Remove ordinary horizontal space before top-level name-part commas. Preserve braced/literal names, quoted parts, control spaces, and unsupported syntax; never reorder names. |
| `journal-fields` | On MR-marked entries, treat a nonempty `journal` + `fjournal` pair as short title and full title respectively. Migrate both atomically to `shortjournal` + `journaltitle`; preserve the pair if either destination conflicts. |
| `book-pagination` | On MR-marked `@book` entries, migrate a positive page count or canonical Roman-plus-Arabic extent from `pages` to `pagetotal` without changing its string. Require no `chapter`, only absent or `page` pagination units, and no conflicting total. Preserve ranges and other unsupported forms. |
| `isbn` | Convert checksum-valid bare ISBN-10 values to contiguous ISBN-13 digits. Validate the entire comma-separated field before conversion or deduplication; preserve annotated, malformed, or invalid fields unchanged. Do not infer hyphenation. |
| `trivial-url` | Remove a bare approved DOI resolver URL matching a DOI or the explicit arXiv eprint's derived DOI, and exact arXiv abstract links. Apply the same cleanup to JSON URLs. Preserve PDF selection, query strings, fragments, ports/userinfo, non-ASCII DOI case differences, and distinct identifiers. |
| `arxiv-doi` | Remove a DOI derived from the matching explicit arXiv eprint, including its exact version. Prune redundant JSON DOI values too. Preserve publisher DOIs, mismatches, conflicting eprint aliases, and unsupported content. |

Field names are matched case-insensitively. Duplicate fields are rejected
before any normalization. Unsupported year/ISBN values, conflicting eprint
aliases, unmarked/incomplete/conflicting journal pairs, and unsupported book
extents produce diagnostics without guessing a repair. The text passes precede
journal migration so compatible
accent spellings do not defer migration until a second run. See the
[BibLaTeX manual](https://mirrors.ctan.org/macros/latex/contrib/biblatex/doc/biblatex.pdf)
for field aliases and date conventions.

DOI URL cleanup uses the same DOI comparison semantics as identifier handling,
including after `add` canonicalizes an incoming DOI. It does not rewrite stored
legacy DOI values or their exact identifier provenance. For example, an uppercase
DOI URL is redundant with its lowercase ASCII DOI, but non-ASCII case folding
is not permitted. URL cleanup runs before arXiv DOI cleanup so both redundant
fields disappear in one default `all` pass.

Redundant DOI/URL values are also pruned from identifier JSON, including
JSON-only leftovers from earlier imports and non-main values in reviewed
staging companions. Existing canonical keys and aliases are never renamed:
an exact identifier needed by `main_identifier` or `key_history` is retained
with a diagnostic. A redundant primary with distinct remaining alternates is
also retained rather than silently promoting an alternate. Other identifiers
and the add-order ledger remain unchanged. JSON removals appear in change
details as `identifiers.<kind>` or `identifier_alternates.<kind>[<index>]`.

MR reviewer cleanup is field-specific: `Victor\ Mikhailovich\ Adukov` becomes
`Victor Mikhailovich Adukov` in `mrreviewer`, not in arbitrary text or math.
The lexer recognizes actual control-space tokens; escaped backslashes and
unsupported contexts remain unchanged. A replacement that would turn a visible
space into a swallowed control-word delimiter is also left unchanged.

The `@misc` to `@online` conversion is an explicit arXiv import convention,
not a rule for every record available on arXiv. Existing `@article`, `@book`,
and other types are not reclassified. A URL alone, missing/blank eprint, or
conflicting eprint aliases does not enable the conversion. `template` and
`add` use this same rule; dry-run change reports show the entry-type change,
and staging files themselves remain unchanged until normal verified cleanup.

Both MR-specific rules require at least one nonempty `mrnumber`, `mrclass`, or
`mrreviewer` field in the BibLaTeX entry itself. The pair alone, URLs, citekeys,
similar field names, and JSON-only MR identifiers do not qualify. This is the
accepted local MR-import convention, not independent verification of origin.
Unmarked entries are never rewritten by these two actions. A lone `journal`
or `fjournal` is also left unchanged, even if a modern field has equal text.
Text normalization does not evaluate arbitrary TeX: unsupported commands,
math, comments, verbatim, malformed syntax, and token-sensitive unbraced wrapper
arguments remain untouched. A recognized accent command consumes its own
argument braces: `Z\'{u}\~{n}iga` becomes `Zúñiga`. Independent outer groups and
formatting arguments remain: `{\c{c}}` becomes `{ç}`, and
`\textbf{\'{E}}` becomes `\textbf{É}`. No generic brace stripping is performed.

`publisher-location` remains removed and rejected. Comma position does not
establish a publisher's location; `publisher = {Springer, Cham}` is not split
automatically. Numeric `pages` alone does not enable book-pagination migration:
the MR metadata and whole-book extent checks above are also required.

ISBN-10 conversion now emits digits without reconstructing hyphen groups.
This changes automatically selected ISBN-based citekeys for new imports.
Existing citekeys and exact identifier-ledger values remain unchanged;
already-reviewed companions retain their selected exact identifiers when
equivalent to the normalized ISBN.

Normalization changes presentation metadata in `library.bib` while loading
and validating the complete workspace. It preserves identifier-ledger and
add-order bytes when their data is unchanged.

### Reconcile missing identifier projections

```powershell
biblio reconcile --dry-run
biblio reconcile
biblio validate
```

`reconcile` is an explicit one-way upgrade and repair operation. For each
supported identifier projected by `library.bib` but absent from that record's
JSON inventory, it appends the exact `.bib` value to
`identifier_collection.json`. If the identifier kind already has a different
primary value, the missing exact value is appended to
`identifier_alternates`.

The operation never overwrites or deletes an inventory value, changes
`main_identifier`, changes citekey/hash provenance, modifies `library.bib`, or
modifies `add_order.json`. Unknown identifier kinds remain blocked rather than
being guessed. Use the dry-run report to review additions before apply.

### Remove

```powershell
biblio remove KEY --dry-run
biblio remove KEY
```

`KEY` may be a canonical citekey or BibLaTeX alias. Apply hard-deletes the
active record from `library.bib`, its exact identifier record, and its active
chronology position. Git or another consumer-owned history system provides
historical recovery for intentional removal.

### Promote an arXiv record

```powershell
biblio promote OLD_KEY published-record.bib --dry-run
biblio promote OLD_KEY published-record.bib
```

The payload must contain exactly one published record and one publisher DOI.
Promotion installs a DOI-derived canonical citekey, keeps the old arXiv key as
a BibLaTeX `ids` alias, retains exact arXiv/DOI identifier provenance through
`identifier_alternates` and `key_history`, and preserves the record's
chronological position. Existing documents may continue citing the old key.
An arXiv-derived DOI such as `10.48550/arXiv...` is rejected as the publisher
DOI.

### Recover a coordinated transaction

```powershell
biblio recover --status
biblio recover --dry-run
biblio recover
```

`--status` and `--dry-run` inspect the workspace coordinator without changing
it. Apply recovers the whole three-artifact vector, choosing the recorded
original or candidate state from the transaction's last changed artifact
(`library.bib` is installed last whenever it changes) and repairing the other
artifacts consistently. Recovery also completes pending transaction-artifact
cleanup. Do not delete coordinator, candidate, shadow, or lock files manually.

## Retired surfaces

The following commands are intentionally absent:

- `sort`: alphabetical mutation conflicts with chronological physical order.
- `sync`: ambiguous or bidirectional synchronization is retired. The narrow
  `reconcile` command only appends missing supported `.bib` projections to the
  JSON inventory and has no reverse direction.
- `generate-labels`: add and promote derive keys transactionally.
- migration-away commands: identifier and order artifacts remain required
  normal-runtime authorities.

## Safety and history

- The engine is Git-independent. It never invokes Git or requires a checkout.
- The engine does not create timestamped backups or archive copies. Consumers
  choose their own history system.
- Multi-file writes use a coordinator, per-artifact digest evidence, ordered
  replacement, and explicit recovery. They fail closed when the workspace
  cannot be proved consistent.
- Use `--dry-run` before add, normalize, reconcile, remove, or promote when
  reviewing a change.
- Test engine changes with fixtures or temporary workspaces, never against a
  consumer's production data.
- Text is UTF-8; deterministic engine writes use LF line endings and one final
  newline.

Clean mutations intentionally retain hidden lock, coordinator, and resolution
evidence beside workspace artifacts. These files make later proof and recovery
possible; their presence does not mean a transaction is unresolved. The
engine is Git-independent, and `biblio init` deliberately does not create or
edit `.gitignore`. A Git-based consumer may ignore the exact internal patterns:

```gitignore
**/.*.biblio.lock
**/.*.biblio-workspace.json
**/.*.biblio-workspace-resolved.json
**/.*.biblio-workspace-*.candidate
**/.*.biblio-workspace-*.original
**/.biblio-add-cleanup.json
```

Candidate, original, and cleanup-receipt files normally exist only while work
or cleanup is pending, but they are included because unresolved evidence must
not enter commits. Ignoring evidence never authorizes deleting it. Inspect with
`biblio recover --status` and resolve with `biblio recover`; never manually
delete an unresolved coordinator, resolution record, candidate, original,
cleanup receipt, or lock sidecar.

[`pre-commit-data-hooks.yaml`](pre-commit-data-hooks.yaml) is an optional
consumer template. Its coordinated hooks run when any of the three artifacts
changes; the template is not this engine repository's own hook configuration.

## Development

```powershell
uv sync --dev
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv build
```

The wheel contains `src/biblio`. Tests use temporary workspaces; the marked
biber integration test additionally requires biber.

## License

MIT. See [LICENSE](LICENSE).

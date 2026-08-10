# biblio

`biblio` is a Python 3.13 command-line engine for maintaining BibLaTeX
workspaces. It validates related data files, generates stable citekeys, imports
staged entries, synchronizes identifiers, sorts records, and normalizes common
metadata problems.

This repository ships the engine, its schema, tests, and an optional consumer
hook template. It does **not** ship a production bibliography, manuscript
sources, TeX styles, or LaTeX examples.

## Primary consumer

The principal consumer is
[`KiringYJ/tex-studies`](https://github.com/KiringYJ/tex-studies), whose local
Windows checkout is `D:\tex-studies` in the maintainer workspace.
`tex-studies` installs this repository as a Git dependency and owns the live
bibliography data, TeX formatting, biber builds, and publication exports.

Its `biblio.toml` maps the engine to consumer-owned files:

```toml
[paths]
bib = "shared/bibtex/bib/library.bib"
identifiers = "shared/data/identifier_collection.json"
add_order = "shared/data/add_order.json"
staging = "shared/bibtex/bib/staging"
```

That division is intentional:

- `biblio` owns bibliography-maintenance behavior and validation rules.
- Consumer repositories own their records, path layout, citation policy, and
  document build system.

## Capabilities

- Validate citekey consistency across the `.bib` file, identifier metadata,
  and addition-order ledger.
- Generate deterministic `lastname-year-hash` citekeys with collision
  handling.
- Create identifier JSON templates for staged `.bib` files.
- Add staged records while updating all three canonical data files together.
- Sort records alphabetically or by addition order.
- Synchronize identifiers such as DOI, ISBN, MR, ZBL, arXiv, and URL values
  into BibLaTeX entries.
- Normalize legacy dates, publisher/location pairs, eprint fields, LaTeX
  accents, ISBNs, and redundant DOI/arXiv URLs.
- Operate against different workspace layouts through `biblio.toml` or CLI
  path overrides.

CSL-JSON export, classic BibTeX conversion, remote enrichment, duplicate
detection, and citation analysis are roadmap items rather than current
features; see [TODO.md](TODO.md).

## Installation

For development:

```powershell
git clone https://github.com/KiringYJ/biblatex-library.git
Set-Location biblatex-library
uv sync --dev
uv run biblio --help
```

A consumer project can declare the Git dependency directly:

```toml
[project]
dependencies = [
  "biblio @ git+https://github.com/KiringYJ/biblatex-library",
]
```

Pin the resolved revision in the consumer lockfile.

## Workspace model

The engine operates on four configured paths:

| Path | Role |
|---|---|
| `bib` | Canonical BibLaTeX `.bib` file |
| `identifiers` | JSON object containing external identifiers by citekey |
| `add_order` | JSON array recording citekeys in addition order |
| `staging` | Incoming `.bib` files and their identifier JSON companions |

Paths in `biblio.toml` are resolved relative to that file. Without a config,
the CLI uses these defaults relative to the current workspace:

```text
bib/library.bib
data/identifier_collection.json
data/add_order.json
staging/
```

Create an empty consumer workspace with:

```powershell
biblio init D:\path\to\bibliography-workspace
```

`biblio init` creates the default directories and empty data files in the
target workspace. Those directories are runtime data owned by the consumer;
they are not source directories in this engine repository.

## Commands

| Command | Purpose |
|---|---|
| `biblio init [DIR]` | Initialize a consumer workspace |
| `biblio validate` | Check three-file citekey consistency and generated labels |
| `biblio validate --fix` | Rename inconsistent citekeys after consistency checks pass |
| `biblio template` | Generate identifier JSON companions for staged `.bib` files |
| `biblio add` | Import valid staging pairs into the canonical files |
| `biblio generate-labels` | Write deterministic citekey mappings |
| `biblio sort alphabetical` | Sort the `.bib` and identifier map by citekey |
| `biblio sort add-order` | Sort them according to the addition-order ledger |
| `biblio sync --dry-run` | Preview identifier-to-BibLaTeX synchronization |
| `biblio sync` | Apply identifier-to-BibLaTeX synchronization |
| `biblio normalize [ACTION] --dry-run` | Preview one or all normalization passes |
| `biblio normalize [ACTION]` | Apply one or all normalization passes |

Normalization actions are:

- `year-to-date`
- `publisher-location`
- `eprint-fields`
- `latex-accents`
- `isbn`
- `trivial-url`

Global options must precede the subcommand:

```text
--config PATH       Select a biblio.toml file
--bib PATH          Override the canonical .bib path
--identifiers PATH  Override the identifier JSON path
--add-order PATH    Override the addition-order JSON path
-v / -vv            Enable informational or debug logging
```

For example:

```powershell
biblio --config D:\tex-studies\biblio.toml validate
biblio --bib D:\other-workspace\references.bib normalize trivial-url --dry-run
```

## Staging workflow

Staged files use matching stems, conventionally
`YYYY-MM-DD-description.bib` and `YYYY-MM-DD-description.json`.

```powershell
# Generate missing JSON companions from staged .bib files.
biblio template

# Review and validate the current workspace.
biblio validate

# Import complete pairs. The add command creates a timestamped backup first.
biblio add

# Confirm the resulting three-file state.
biblio validate
```

The three canonical files form one integrity set. Adding, removing, renaming,
or reordering citekeys must preserve agreement between the `.bib` file,
identifier map, and addition-order ledger.

## Safety boundaries

- Keep consumer bibliography data under version control.
- Use `--dry-run` for synchronization and normalization before applying
  changes.
- `biblio add` creates a timestamped backup under the configured staging
  directory before modifying canonical files.
- Test engine changes only with pytest fixtures or temporary workspaces, never
  against a consumer's production bibliography.
- All text and JSON I/O is UTF-8; JSON is written without ASCII escaping.
- Parse and serialize bibliography data through `bibtexparser` rather than
  hand-written regular expressions.

[`pre-commit-data-hooks.yaml`](pre-commit-data-hooks.yaml) contains optional
consumer-side hooks for the default scaffold layout. Copy and adapt those hooks
in the consumer repository; they are not part of this engine's own pre-commit
pipeline.

## Development

The wheel contains only `src/biblio`. Repository tests use temporary
workspaces, so development does not require a live bibliography or TeX
installation.

```powershell
uv sync --dev
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv build
```

Main source areas:

```text
src/biblio/        CLI, configuration, domain operations, and bundled schema
tests/             Unit and integration-style tests using temporary data
typings/           Local type stubs for external packages
```

## License

MIT. See [LICENSE](LICENSE).

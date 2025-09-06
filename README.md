# biblatex-library

A curated bibliographic database with production-grade tooling for validation, normalization, conversion, and enrichment. Maintains consistency across biblatex, CSL-JSON, and BibTeX formats.

## Overview

This repository provides:

- **Curated bibliographic database** (`bib/library.bib`) in biblatex format
- **Python tooling** (`blx` CLI) for validation, conversion, and maintenance
- **LaTeX examples** demonstrating different citation styles
- **Custom biblatex style** (`biblatex-yj`)
- **CSL-JSON conversion** for interoperability with Pandoc and other tools

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/KiringYJ/biblatex-library.git
cd biblatex-library

# Create virtual environment and install
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

### Basic Usage

```bash
# Validate library consistency
blx validate

# Validate with verbose output
blx -v validate

# Generate labels for entries
blx generate-labels

# Generate labels with custom output
blx generate-labels -o my_labels.json

# Validate specific workspace
blx --workspace /path/to/project validate
```

## The `blx` CLI Tool

The `blx` command-line tool provides utilities for maintaining the bibliographic library.

### Validation

The `validate` command checks consistency across all data sources:

```bash
blx validate [options]
```

**What it validates:**
- **Citekey consistency** - Ensures `bib/library.bib`, `data/add_order.json`, and `data/identifier_collection.json` contain the same set of citekeys
- **JSON Schema validation** - Validates data files against their schemas
- **Biber compatibility** - Checks that the .bib file can be processed by biber

**Options:**
- `-v, --verbose` - Show INFO level messages (use `-vv` for DEBUG)
- `--workspace WORKSPACE` - Specify workspace directory (default: current directory)

**Examples:**

```bash
# Basic validation (quiet output)
blx validate

# Verbose validation showing progress
blx -v validate

# Debug validation with detailed logging
blx -vv validate

# Validate a different project
blx --workspace /path/to/other/project validate
```

**Exit codes:**
- `0` - All validation checks passed
- `1` - Validation failed or error occurred

**Sample output:**

```
# Successful validation
$ blx -v validate
INFO biblib.cli:34 – Starting validation checks
INFO biblib.validate:134 – Validating citekey consistency across data sources
INFO biblib.validate:183 – ✓ All 195 citekeys are consistent across data sources
INFO biblib.cli:43 – ✓ All validation checks passed

# Failed validation
$ blx -v validate
INFO biblib.cli:34 – Starting validation checks
INFO biblib.validate:134 – Validating citekey consistency across data sources
ERROR biblib.validate:156 – Missing from library.bib: ['missing-key-2025']
ERROR biblib.validate:164 – Missing from identifier_collection.json: ['missing-key-2025']
ERROR biblib.validate:174 – Only in add_order.json: ['missing-key-2025']
ERROR biblib.validate:185 – ✗ Citekey inconsistencies found across data sources
ERROR biblib.cli:46 – ✗ Validation checks failed
```

### Label Generation

The `generate-labels` command creates citekeys in the format `lastname-year-<hash>`:

```bash
blx generate-labels [options]
```

**What it generates:**
- **lastname** - Extracted from author/editor field, normalized and cleaned
- **year** - Extracted from date/year field (4-digit years only)
- **hash** - 8-character SHA-256 hash of the main identifier from identifier_collection.json

**Options:**
- `-o OUTPUT, --output OUTPUT` - Output file path (default: bib/generated/labels.json)
- `-v, --verbose` - Show INFO level messages (use `-vv` for DEBUG)
- `--workspace WORKSPACE` - Specify workspace directory (default: current directory)

**Examples:**

```bash
# Generate labels with default output
blx generate-labels

# Generate labels with custom output file
blx generate-labels -o my_labels.json

# Generate labels with verbose output
blx -v generate-labels

# Generate labels for different project
blx --workspace /path/to/project generate-labels
```

**Sample output:**

```
$ blx -v generate-labels
INFO biblib.cli:37 – Generating labels for biblatex entries
INFO biblib.generate:211 – Generating labels for biblatex entries
INFO biblib.generate:245 – Generated 195 labels
INFO biblib.cli:50 – ✓ Generated 195 labels
INFO biblib.cli:51 – ✓ Saved to: bib\generated\labels.json
INFO biblib.cli:55 – Sample labels:
INFO biblib.cli:59 –   bredon-1993-7908a921 -> bredon-1993-7908a921
INFO biblib.cli:59 –   dubrovin-1985-b24c3982 -> dubrovin-1985-b24c3982
```

The generated JSON file maps original entry keys to suggested labels. This is useful for:
- **Standardizing citekeys** across different bibliography files
- **Generating consistent labels** for new entries  
- **Auditing existing labels** for consistency

**Exit codes:**
- `0` - Labels generated successfully
- `1` - Generation failed or error occurred

## Repository Structure

```
biblatex-library/
├── bib/
│   ├── library.bib                 # Canonical bibliographic database
│   └── generated/                  # Derived exports (auto-generated)
├── data/
│   ├── add_order.json              # Chronological addition order
│   └── identifier_collection.json # External identifier mappings
├── src/
│   └── biblib/                     # Python package
│       ├── cli.py                  # Command-line interface
│       ├── validate.py             # Validation logic
│       └── ...                     # Other modules
├── tests/                          # Test suite
├── latex/examples/                 # LaTeX demonstration documents
└── tex/biblatex-yj/               # Custom biblatex style
```

## Data Files

### `bib/library.bib`
The **single source of truth** - a curated bibliography in biblatex format. Uses modern biblatex entry types like `@online` and `@thesis`.

### `data/add_order.json`
An **append-only ledger** tracking the chronological order of entry additions. Used for stable sorting and history tracking.

### `data/identifier_collection.json`
External identifiers (DOI, ISBN, arXiv, etc.) for bibliography entries, enabling enrichment and deduplication.

## Development

### Quality Gates

Before committing, ensure all quality checks pass:

```bash
# 1. Lint and auto-fix
ruff check . --fix

# 2. Format code
ruff format .

# 3. Type check
pyright

# 4. Run tests
pytest

# 5. Validate library
blx validate
```

### Type Checking Configuration

This project uses **strict type checking** to ensure code quality:

- **pyright** and **Pylance** are configured to use `strict` mode
- Both tools use identical strictness settings to avoid inconsistencies
- Configuration files:
  - `pyrightconfig.json` - pyright/Pylance settings
  - `.vscode/settings.json` - VS Code workspace settings

**Key type checking rules:**
- `reportUnknownArgumentType: error` - Catch untyped function arguments
- `reportUnknownVariableType: error` - Catch variables with unknown types
- `reportUnusedImport: error` - Remove unused imports
- `reportUnusedVariable: error` - Remove unused variables

This ensures **consistent type checking** across different development environments and tools.

### Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=biblib

# Run specific test file
pytest tests/test_validate.py -v
```

## LaTeX Usage

### biblatex Examples

```bash
cd latex/examples/biblatex-spbasic/
latexmk -pdf -xelatex main.tex
```

### amsrefs Examples

```bash
cd latex/examples/amsrefs-bibtex/
latexmk -pdf -xelatex -bibtex main.tex
```

## Contributing

1. **Validation first** - Always run `blx validate` before committing
2. **Quality gates** - Ensure ruff, pyright, and tests pass
3. **Small PRs** - Keep changes focused and bisectable
4. **Tests required** - Add tests for any behavior changes

See `CLAUDE.md` for detailed development guidelines.

## License

MIT License. See `LICENSE` for details.
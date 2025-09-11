# biblatex-library

A production-grade bibliographic database with powerful Python tooling for validation, maintenance, and workflow automation. Features robust type safety, comprehensive error handling, and enterprise-level data integrity controls.

## Features

✨ **Core Capabilities**
- **Curated bibliographic database** (`bib/library.bib`) with 190+ high-quality entries
- **Professional Python tooling** (`blx` CLI) with zero-error type safety
- **Automatic validation** ensuring data consistency across all formats
- **Smart citekey generation** with collision detection and stable identifiers
- **Staging workflow** for safe batch operations with automatic backup

🔧 **Production-Ready Architecture**
- **Comprehensive error handling** with specific exception types
- **Configuration management** with centralized workspace paths
- **Type-safe operations** validated by strict pyright configuration
- **Atomic backup system** protecting against data corruption
- **Modular design** with focused, single-responsibility functions

📚 **Format Support**
- **biblatex format** (primary) with full Unicode support
- **CSL-JSON conversion** for Pandoc and Zotero integration
- **BibTeX compatibility** for legacy workflows
- **Custom biblatex style** (`biblatex-yj`) for specialized formatting

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/KiringYJ/biblatex-library.git
cd biblatex-library

# Install with UV (recommended)
uv sync

# Or with pip
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

### Essential Commands

```bash
# Validate entire database (comprehensive checks)
uv run blx validate

# Add new entries from staging directory
uv run blx add

# Generate staging templates from .bib files
uv run blx template

# Generate consistent citekey labels
uv run blx generate-labels

# Sort database alphabetically by citekey
uv run blx sort alphabetical

# Sort database by chronological add order
uv run blx sort add-order

# Verbose validation with detailed progress
uv run blx -v validate

# Automatically fix citekey mismatches
uv run blx validate --fix

# Work with different project workspace
uv run blx --workspace /path/to/project validate
```

## The `blx` CLI Tool

The `blx` command-line tool provides enterprise-grade utilities for bibliography management with comprehensive validation, error handling, and data safety features.

### Core Commands

#### Validation (`blx validate`)

Performs comprehensive consistency checks across all data sources:

```bash
uv run blx validate [--fix] [--workspace PATH]
```

**Validation Checks:**
- ✅ **Citekey consistency** across `library.bib`, `identifier_collection.json`, and `add_order.json`
- ✅ **Label validation** ensuring citekeys match generated format (`lastname-year-hash`)
- ✅ **JSON Schema compliance** for all data files
- ✅ **Biber compatibility** verification for LaTeX processing
- ✅ **Unicode encoding** validation for international characters

**Options:**
- `--fix` - Automatically repair mismatched citekeys
- `--workspace PATH` - Specify different project directory
- `-v, --verbose` - Show detailed progress information
- `-vv` - Enable debug-level logging

#### Adding Entries (`blx add`)

Safely processes entries from the staging directory with automatic backup:

```bash
uv run blx add [--workspace PATH]
```

**Process Flow:**
1. 🔍 **Scans** `staging/` for matching `.bib` and `.json` file pairs
2. 💾 **Creates automatic backup** with timestamp
3. 🔍 **Validates** new entries against existing database
4. 🏷️ **Generates** consistent citekeys with collision detection
5. ✅ **Appends** entries to all three data files atomically
6. 🗑️ **Cleans up** processed staging files

**File Naming Pattern:** `YYYY-MM-DD-description.(bib|json)`

#### Template Generation (`blx template`)

Generates identifier collection JSON templates from staging .bib files to streamline the staging workflow:

```bash
uv run blx template [--overwrite] [--workspace PATH]
```

**Process Flow:**
1. 🔍 **Scans** `staging/` directory for `.bib` files
2. 📖 **Parses** bibliographic entries to extract identifiers
3. 🏷️ **Determines** main identifier using priority order: `doi` > `isbn` > `mrnumber` > `url`
4. 📝 **Generates** corresponding `.json` template files
5. ⚡ **Skips** existing `.json` files (unless `--overwrite` is used)

**Identifier Priority:**
- **DOI** (highest priority) - Digital Object Identifier
- **ISBN** - International Standard Book Number
- **MR Number** - Mathematical Reviews number
- **URL** (lowest priority) - Web address

**Features:**
- 🎯 **Automated workflow** - No manual JSON creation needed
- 🔄 **Safe defaults** - Skips existing files to prevent overwrites
- 📋 **Template structure** - Generates proper `identifier_collection.json` format
- 🌍 **Unicode support** - Handles international bibliography entries

**File Processing:** For each `staging/example.bib`, generates `staging/example.json` with extracted identifiers and automatically selected main identifier.

#### Label Generation (`blx generate-labels`)

Creates consistent citekey labels for bibliographic entries:

```bash
uv run blx generate-labels [-o OUTPUT] [--workspace PATH]
```

**Features:**
- 🎯 **Deterministic** label generation: `lastname-year-hash8`
- � **Shorthand priority**: Uses `shorthand` field when available instead of author lastname
- �🔄 **Collision handling** with automatic hash adjustment
- 📝 **JSON output** mapping original keys to generated labels
- 🌍 **Unicode support** for international author names

#### Sorting (`blx sort`)

Reorders database entries with data integrity protection:

```bash
# Sort alphabetically by citekey (recommended)
uv run blx sort alphabetical

# Sort by chronological add order
uv run blx sort add-order
```

**Safety Features:**
- 💾 **Automatic backup** before any modifications
- 🔒 **Atomic operations** across all three data files
- ✅ **Validation** after sorting to ensure consistency

### Advanced Usage

#### Working with Multiple Projects

```bash
# Set workspace for all commands
export BIBLIB_WORKSPACE=/path/to/project
uv run blx validate

# Or specify per command
uv run blx --workspace /path/to/project validate
```

#### Staging Workflow

1. **Prepare entries** in `staging/` directory:
   ```
   staging/
   ├── 2024-01-15-new-paper.bib      # Bibliography entry
   ├── 2024-01-15-new-paper.json     # Identifier metadata
   ├── 2024-01-20-conference.bib
   └── 2024-01-20-conference.json
   ```

2. **Validate** before adding:
   ```bash
   uv run blx validate
   ```

3. **Process** staging files:
   ```bash
   uv run blx add
   ```

4. **Verify** results:
   ```bash
   uv run blx validate
INFO biblib.validate:303 – ✓ Successfully fixed 2 citekeys
INFO biblib.cli:98 – ✓ All citekey fixes applied successfully
```

### Label Generation

The `generate-labels` command creates citekeys in the format `lastname-year-<hash>`:

```bash
blx generate-labels [options]
```

**What it generates:**
- **lastname** - Extracted from `shorthand` field (preferred) or author/editor lastname, normalized and cleaned
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

### Sorting

The `sort` command reorders `library.bib` and `identifier_collection.json` while preserving `add_order.json`:

```bash
blx sort [mode] [options]
```

**Sorting modes:**
- **`alphabetical`** - Sort entries alphabetically by citekey (default)
- **`add-order`** - Sort entries to match the sequence in `data/add_order.json`

**What it sorts:**
- **library.bib** - Reorders bibliography entries
- **identifier_collection.json** - Reorders identifier mappings
- **add_order.json** - **Never modified** (read-only reference)

**Options:**
- `-v, --verbose` - Show INFO level messages (use `-vv` for DEBUG)
- `--workspace WORKSPACE` - Specify workspace directory (default: current directory)

**Examples:**

```bash
# Sort files alphabetically by citekey
blx sort alphabetical

# Sort files to match add_order.json sequence
blx sort add-order

# Sort with verbose output
blx -v sort alphabetical

# Sort different project
blx --workspace /path/to/project sort add-order
```

**Sample output:**

```
$ blx -v sort alphabetical
INFO biblib.cli:148 – Sorting files alphabetically by citekey
INFO biblib.sort:32 – Sorting files alphabetically by citekey
INFO biblib.sort:46 – ✓ Successfully sorted files alphabetically by citekey
INFO biblib.cli:166 – ✓ Sort operation completed successfully

$ blx -v sort add-order
INFO biblib.cli:156 – Sorting files to match add_order.json sequence
INFO biblib.sort:75 – Sorting files to match add_order.json sequence
INFO biblib.sort:89 – ✓ Successfully sorted files to match add_order.json sequence
INFO biblib.cli:166 – ✓ Sort operation completed successfully
```

**Use cases:**
- **Alphabetical sorting** - For clean, predictable ordering in version control diffs
- **Add-order sorting** - To restore chronological addition order for historical context
- **Consistency maintenance** - Keep all data files synchronized

**Exit codes:**
- `0` - Sorting completed successfully
- `1` - Sorting failed or error occurred

### Template Generation

The `template` command streamlines the staging workflow by automatically generating identifier collection JSON templates from .bib files:

```bash
blx template [options]
```

**What it generates:**
- **JSON templates** - Creates `.json` files for corresponding `.bib` files in staging directory
- **Identifier extraction** - Automatically extracts DOIs, ISBNs, MR numbers, URLs from bibliography entries
- **Main identifier selection** - Uses priority-based selection (doi > isbn > mrnumber > url)

**Options:**
- `--overwrite` - Overwrite existing .json files (default: skip existing files)
- `-v, --verbose` - Show INFO level messages (use `-vv` for DEBUG)
- `--workspace WORKSPACE` - Specify workspace directory (default: current directory)

**Examples:**

```bash
# Generate templates for all .bib files in staging/
blx template

# Generate templates, overwriting existing .json files
blx template --overwrite

# Generate templates with verbose output
blx -v template

# Generate templates for different project
blx --workspace /path/to/project template
```

**Sample output:**

```
$ blx -v template
INFO biblib.cli:302 – Generating identifier collection templates from staging .bib files
INFO biblib.template:156 – Processing staging/2024-01-15-new-paper.bib
INFO biblib.template:187 – Selected main identifier: doi (10.1234/example.2024)
INFO biblib.template:201 – Generated staging/2024-01-15-new-paper.json
INFO biblib.template:156 – Processing staging/2024-01-20-conference.bib
INFO biblib.template:187 – Selected main identifier: url (https://example.com/paper)
INFO biblib.template:201 – Generated staging/2024-01-20-conference.json
INFO biblib.cli:320 – ✓ Generated 2 identifier collection templates
```

**File Processing Example:**

Input: `staging/2024-01-15-paper.bib`
```bibtex
@article{tempkey,
  title = {Example Paper},
  author = {Smith, John},
  year = {2024},
  doi = {10.1234/example.2024},
  url = {https://example.com/paper}
}
```

Generated: `staging/2024-01-15-paper.json`
```json
{
  "tempkey": {
    "main_identifier": "10.1234/example.2024",
    "identifiers": {
      "doi": "10.1234/example.2024",
      "url": "https://example.com/paper"
    }
  }
}
```

**Use cases:**
- **Streamlined staging** - Eliminate manual JSON creation for new entries
- **Consistent workflow** - Ensure all staging files have proper identifier metadata
- **Batch processing** - Generate templates for multiple bibliography files at once
- **Error prevention** - Avoid missing identifier files when adding entries

**Exit codes:**
- `0` - Templates generated successfully
- `1` - Generation failed or error occurred

## Architecture & Data Safety

### Production-Grade Design

The biblatex-library employs enterprise-level architecture patterns ensuring data integrity and operational reliability:

**🛡️ Type Safety & Error Handling**
- **Zero-error policy**: All code passes strict `pyright` type checking
- **Specific exception types**: `BackupError`, `FileOperationError`, `InvalidDataError`
- **Graceful failure handling**: No silent errors or data corruption
- **Comprehensive logging**: Structured logs for debugging and monitoring

**📁 Workspace Configuration**
- **Centralized paths**: `WorkspaceConfig` eliminates hardcoded file locations
- **Flexible deployment**: Easy adaptation to different project structures
- **Cross-platform support**: Works on Windows, macOS, and Linux

**🔄 Atomic Operations**
- **Triple-file consistency**: `library.bib`, `identifier_collection.json`, `add_order.json`
- **Automatic backups**: Timestamped snapshots before any data modification
- **Rollback capability**: Easy recovery from backup files
- **Transaction-like behavior**: All-or-nothing operations prevent partial corruption

### Data Files Structure

The bibliography system maintains three synchronized data files:

1. **`bib/library.bib`** - Primary bibliography in biblatex format
   - Full bibliographic entries with all metadata
   - Unicode support for international characters
   - Compatible with biber/biblatex processing

2. **`data/identifier_collection.json`** - Structured identifier metadata
   - DOIs, URLs, arXiv IDs, MR numbers, etc.
   - JSON Schema validated for data integrity
   - Enables API enrichment and verification

3. **`data/add_order.json`** - Chronological entry sequence
   - Preserves order of entry addition
   - Enables temporal sorting and analysis
   - Supports historical reconstruction

### Quality Assurance

**🔍 Comprehensive Validation**
- Citekey consistency across all three files
- JSON Schema compliance for structured data
- Unicode encoding verification
- Biber processing compatibility
- Label format standardization

**⚡ Performance & Reliability**
- Modular function design (focused, single-responsibility)
- Efficient file I/O with explicit UTF-8 encoding
- Memory-conscious processing for large datasets
- Robust error recovery and logging

**🧪 Testing & Verification**
- Full test suite with 45+ test cases
- Integration tests with real file operations
- Type safety verified through static analysis
- Continuous validation in development workflow

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

## Contributing

1. **Validation first** - Always run `blx validate` before committing
2. **Quality gates** - Ensure ruff, pyright, and tests pass
3. **Small PRs** - Keep changes focused and bisectable
4. **Tests required** - Add tests for any behavior changes

See `CLAUDE.md` for detailed development guidelines.

## Roadmap / TODO

### Convert Functionality
- [ ] **biblatex to BibTeX conversion** - Convert modern biblatex entries (`@online`, `@thesis`) to classic BibTeX equivalents (`@misc`, `@phdthesis`) with proper field mapping
  - Entry type conversion: `@online` → `@misc`, `@thesis` → `@phdthesis`/@mastersthesis`
  - Field conversion: `date` → `year`/`month`, `journaltitle` → `journal`, etc.
  - Integration with `biber --tool` for robust processing
  - CLI: `blx convert input.bib output.bib`

### Other Features
- [ ] **CSL-JSON export** - Generate CSL-JSON for Pandoc/Zotero compatibility
- [ ] **Enrichment from APIs** - Auto-fill missing data from CrossRef, arXiv, etc.
- [ ] **Duplicate detection** - Find and merge duplicate entries
- [ ] **Citation analysis** - Generate usage reports and statistics

## License

MIT License. See `LICENSE` for details.

# Output & Logging Guidelines

All output in biblib flows through well-defined channels. Follow these rules to keep stdout clean for command results and stderr informative for humans.

## Output Channels

| Channel | What goes here | How |
|---------|----------------|-----|
| **stdout** | Command results: validation output, generated data | `print()` (CLI layer only) |
| **stderr (structured)** | Operational status, progress, warnings, errors | `logger.info()`, `logger.warning()`, `logger.error()` via `logging` module |

## Rules

### 1. Never use `print()` for status messages

Status updates ("Validating...", "Processing 42 entries", "Sorting...") go to **stderr** via `logger.info()`. Using `print()` pollutes stdout and corrupts piped output.

```python
# WRONG — pollutes stdout
print("Validating entries...")

# RIGHT — goes to stderr via logging
logger.info("Validating entries...")
```

### 2. Reserve `print()` for CLI output only

The only valid uses of `print()` are in the CLI layer (`cli.py`) for deliberate user-facing output. Library code (`src/biblib/*.py`) must never use `print()`.

### 3. Use the `logging` module — never raw `print()` for diagnostics

All diagnostic output must go through `logging` (`logger.info()`, `logger.warning()`, `logger.error()`, `logger.debug()`). This ensures consistent formatting and respects log-level filtering.

### 4. Create per-module loggers

```python
# At the top of each module
import logging
logger = logging.getLogger(__name__)

logger.info(f"processing {count} entries")
logger.warning(f"missing field '{field_name}' in entry {entry_key}")
```

### 5. Choose the right log level

| Level | When to use | Visible by default? |
|-------|-------------|---------------------|
| `error` | Operation failed, cannot recover | Yes (stderr) |
| `warning` | Data issue that degrades results (missing field, encoding fallback) | Yes (stderr) |
| `info` | Major operation status (start/finish, counts, file paths) | No (requires `-v`) |
| `debug` | Detailed calculation state, intermediate values | No (requires `-vv`) |

### 6. Keep debug messages concise

Consolidate related debug values into a single message instead of one line per field.

```python
# WRONG — multiple separate debug calls
logger.debug(f"Entry key: {key}")
logger.debug(f"Entry type: {entry_type}")
logger.debug(f"Field count: {field_count}")

# RIGHT — one structured message
logger.debug(f"Processing entry {key}: type={entry_type}, fields={field_count}")
```

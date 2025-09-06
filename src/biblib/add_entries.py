"""Add new bibliography entries from staging files."""

import json
import logging
import re
import tempfile
from pathlib import Path
from typing import Any

import bibtexparser  # type: ignore[import-untyped]

from .generate import generate_labels
from .validate import extract_citekeys_from_bib, extract_citekeys_from_identifier_collection

logger = logging.getLogger(__name__)


def create_backup(workspace: Path) -> str:
    """Create timestamped backup of core data files.

    Args:
        workspace: Path to the workspace directory

    Returns:
        Backup directory path

    Raises:
        RuntimeError: If backup creation fails
    """
    import datetime

    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = workspace / "staging" / f"backup-{timestamp}"

    try:
        backup_dir.mkdir(parents=True, exist_ok=True)

        # Copy core data files
        bib_path = workspace / "bib" / "library.bib"
        identifier_path = workspace / "data" / "identifier_collection.json"
        add_order_path = workspace / "data" / "add_order.json"

        if bib_path.exists():
            backup_dir.joinpath("library.bib").write_bytes(bib_path.read_bytes())
        if identifier_path.exists():
            backup_dir.joinpath("identifier_collection.json").write_bytes(
                identifier_path.read_bytes()
            )
        if add_order_path.exists():
            backup_dir.joinpath("add_order.json").write_bytes(add_order_path.read_bytes())

        logger.info(f"Backup created at {backup_dir}")
        return str(backup_dir)

    except Exception as e:
        raise RuntimeError(f"Failed to create backup: {e}") from e


# Pattern for staging files: YYYY-MM-DD-<slug>
STAGING_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2}-[a-zA-Z0-9_-]+)\.(bib|json)$")


def find_staging_pairs(staging_dir: Path) -> list[tuple[str, Path, Path]]:
    """Find matching .bib/.json file pairs in staging directory.

    Args:
        staging_dir: Path to staging directory

    Returns:
        List of (slug, bib_path, json_path) tuples for matching pairs
    """
    logger.debug(f"Scanning staging directory: {staging_dir}")

    if not staging_dir.exists():
        logger.warning(f"Staging directory does not exist: {staging_dir}")
        return []

    # Find all files matching the pattern
    files_by_slug: dict[str, dict[str, Path]] = {}

    for file_path in staging_dir.iterdir():
        if not file_path.is_file():
            continue

        match = STAGING_PATTERN.match(file_path.name)
        if not match:
            logger.debug(f"Skipping file with invalid pattern: {file_path.name}")
            continue

        slug, extension = match.groups()

        if slug not in files_by_slug:
            files_by_slug[slug] = {}
        files_by_slug[slug][extension] = file_path

    # Find complete pairs (both .bib and .json)
    pairs: list[tuple[str, Path, Path]] = []
    for slug, files in files_by_slug.items():
        if "bib" in files and "json" in files:
            pairs.append((slug, files["bib"], files["json"]))
            logger.debug(f"Found staging pair: {slug}")
        else:
            missing = [ext for ext in ["bib", "json"] if ext not in files]
            logger.warning(f"Incomplete staging pair for {slug}, missing: {missing}")

    logger.info(f"Found {len(pairs)} complete staging pairs")
    return pairs


def load_existing_keys(bib_path: Path, identifier_path: Path, add_order_path: Path) -> set[str]:
    """Load all existing citekeys from the three data files.

    Args:
        bib_path: Path to library.bib
        identifier_path: Path to identifier_collection.json
        add_order_path: Path to add_order.json

    Returns:
        Set of all existing citekeys
    """
    existing_keys: set[str] = set()

    try:
        if bib_path.exists():
            existing_keys.update(extract_citekeys_from_bib(bib_path))
    except Exception as e:
        logger.error(f"Failed to load keys from {bib_path}: {e}")

    try:
        if identifier_path.exists():
            existing_keys.update(extract_citekeys_from_identifier_collection(identifier_path))
    except Exception as e:
        logger.error(f"Failed to load keys from {identifier_path}: {e}")

    try:
        if add_order_path.exists():
            with open(add_order_path, encoding="utf-8") as f:
                add_order_data: Any = json.load(f)
                if isinstance(add_order_data, list):
                    existing_keys.update(str(key) for key in add_order_data)  # type: ignore[arg-type]
    except Exception as e:
        logger.error(f"Failed to load keys from {add_order_path}: {e}")

    logger.debug(f"Loaded {len(existing_keys)} existing keys")
    return existing_keys


def process_staging_entry(
    slug: str, bib_path: Path, json_path: Path, existing_keys: set[str]
) -> tuple[str, dict[str, Any], dict[str, Any]] | None:
    """Process a single staging entry pair.

    Args:
        slug: The staging file slug (filename without extension)
        bib_path: Path to the .bib file
        json_path: Path to the .json file
        existing_keys: Set of existing citekeys to check for duplicates

    Returns:
        Tuple of (new_key, entry_data, identifier_data) if successful, None if skipped
    """
    logger.info(f"Processing staging entry: {slug}")

    try:
        # Parse the bib file and extract entry data
        logger.debug(f"Parsing bib file: {bib_path}")
        lib = bibtexparser.parse_file(str(bib_path))  # type: ignore[attr-defined]

        if lib.failed_blocks:
            logger.error(f"Failed to parse {bib_path}: {len(lib.failed_blocks)} failed blocks")
            return None

        if len(lib.entries) != 1:
            logger.error(f"Expected exactly 1 entry in {bib_path}, found {len(lib.entries)}")
            return None

        entry = lib.entries[0]
        original_key = entry.key

        # Load identifier data
        logger.debug(f"Loading identifier data: {json_path}")
        with open(json_path, encoding="utf-8") as f:
            identifier_data = json.load(f)

        if not isinstance(identifier_data, dict):
            logger.error(f"Expected object in {json_path}, got {type(identifier_data).__name__}")
            return None

        if original_key not in identifier_data:
            logger.error(f"Entry key '{original_key}' not found in identifier data")
            return None

        # Generate new label
        # Create temporary files for label generation

        # Write entry to temporary bib file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".bib", delete=False, encoding="utf-8"
        ) as temp_bib:
            # Write the entry in proper BibTeX format
            temp_bib.write(f"@{entry.entry_type}{{{original_key},\n")
            for field_name, field_value in entry.fields_dict.items():
                temp_bib.write(f"  {field_name} = {{{field_value.value}}},\n")
            temp_bib.write("}\n")
            temp_bib_path = Path(temp_bib.name)

        # Write identifier to temporary JSON file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as temp_json:
            json.dump({original_key: identifier_data}, temp_json, indent=2)
            temp_json_path = Path(temp_json.name)

        try:
            generated_labels = generate_labels(temp_bib_path, temp_json_path)
        finally:
            # Clean up temporary files
            temp_bib_path.unlink(missing_ok=True)
            temp_json_path.unlink(missing_ok=True)

        if original_key not in generated_labels:
            logger.error(f"Failed to generate label for {original_key}")
            return None

        new_key = generated_labels[original_key]

        # Check for duplicates
        if new_key in existing_keys:
            logger.warning(f"Skipping duplicate key: {new_key} (from {slug})")
            return None

        logger.info(f"Generated new key: {original_key} -> {new_key}")

        # Update entry with new key
        entry.key = new_key

        # Prepare return data
        new_entry_data: dict[str, Any] = {new_key: entry}
        new_identifier_data: dict[str, Any] = {new_key: identifier_data[original_key]}

        return new_key, new_entry_data, new_identifier_data

    except Exception as e:
        logger.error(f"Error processing {slug}: {e}")
        return None


def append_to_files(
    new_entries: list[tuple[str, dict[str, Any], dict[str, Any]]],
    bib_path: Path,
    identifier_path: Path,
    add_order_path: Path,
) -> bool:
    """Append new entries to the three data files.

    Args:
        new_entries: List of (key, entry_data, identifier_data) tuples
        bib_path: Path to library.bib
        identifier_path: Path to identifier_collection.json
        add_order_path: Path to add_order.json

    Returns:
        True if successful, False otherwise
    """
    if not new_entries:
        logger.info("No new entries to append")
        return True

    logger.info(f"Appending {len(new_entries)} new entries to data files")

    # MANDATORY: Create backup before any data file modification
    workspace = bib_path.parent.parent  # Go up from bib/ to workspace
    try:
        backup_path = create_backup(workspace)
        logger.info(f"✓ Backup created: {backup_path}")
    except RuntimeError as e:
        logger.error(f"✗ Backup failed: {e}")
        return False

    try:
        # Load existing data
        if bib_path.exists():
            library = bibtexparser.parse_file(str(bib_path))  # type: ignore[attr-defined]
        else:
            library = bibtexparser.Library()  # type: ignore[attr-defined]

        identifier_collection: dict[str, Any] = {}
        if identifier_path.exists():
            with open(identifier_path, encoding="utf-8") as f:
                identifier_collection = json.load(f)

        add_order: list[str] = []
        if add_order_path.exists():
            with open(add_order_path, encoding="utf-8") as f:
                add_order = json.load(f)

        # Add new entries
        for new_key, entry_data, identifier_data in new_entries:
            logger.debug(f"Processing entry: {new_key}")
            logger.debug(f"Entry data type: {type(entry_data)}")
            logger.debug(
                f"Entry data keys: {list(entry_data.keys()) if hasattr(entry_data, 'keys') else 'Not a dict'}"  # noqa: E501
            )

            # Add to library
            for entry_key, entry in entry_data.items():
                logger.debug(f"Adding entry {entry_key} of type {type(entry)}")
                library.add(entry)  # Use library.add() instead of library.entries.append()

            # Add to identifier collection
            identifier_collection.update(identifier_data)

            # Add to add_order
            add_order.append(new_key)

            logger.debug(f"Added entry: {new_key}")

        # Write back to files with UTF-8 encoding
        bib_string = bibtexparser.write_string(library)  # type: ignore[attr-defined]
        with open(bib_path, "w", encoding="utf-8") as f:
            f.write(bib_string)

        with open(identifier_path, "w", encoding="utf-8") as f:
            json.dump(identifier_collection, f, indent=2, ensure_ascii=False)

        with open(add_order_path, "w", encoding="utf-8") as f:
            json.dump(add_order, f, indent=2, ensure_ascii=False)

        logger.info(f"Successfully appended {len(new_entries)} entries")
        return True

    except Exception as e:
        logger.error(f"Failed to append entries: {e}")
        return False


def add_entries_from_staging(workspace: Path) -> tuple[bool, list[str]]:
    """Add new entries from staging directory to the main data files.

    Args:
        workspace: Path to the workspace root

    Returns:
        Tuple of (success, list_of_processed_slugs)
    """
    logger.info("Starting add entries from staging workflow")

    # Define paths
    staging_dir = workspace / "staging"
    bib_path = workspace / "bib" / "library.bib"
    identifier_path = workspace / "data" / "identifier_collection.json"
    add_order_path = workspace / "data" / "add_order.json"

    # Find staging pairs
    pairs = find_staging_pairs(staging_dir)
    if not pairs:
        logger.info("No staging pairs found")
        return True, []

    # Load existing keys
    existing_keys = load_existing_keys(bib_path, identifier_path, add_order_path)

    # Process each pair
    new_entries: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    processed_slugs: list[str] = []

    for slug, bib_file, json_file in pairs:
        result = process_staging_entry(slug, bib_file, json_file, existing_keys)
        if result is not None:
            new_key, entry_data, identifier_data = result
            new_entries.append((new_key, entry_data, identifier_data))
            processed_slugs.append(slug)
            existing_keys.add(new_key)  # Prevent duplicates within the batch
        else:
            logger.warning(f"Skipped staging pair: {slug}")

    if not new_entries:
        logger.info("No new entries to add")
        return True, []

    # Append to data files
    success = append_to_files(new_entries, bib_path, identifier_path, add_order_path)

    if success:
        # Delete processed staging files
        for slug in processed_slugs:
            bib_file = staging_dir / f"{slug}.bib"
            json_file = staging_dir / f"{slug}.json"

            try:
                bib_file.unlink()
                json_file.unlink()
                logger.info(f"Deleted processed staging files: {slug}")
            except Exception as e:
                logger.error(f"Failed to delete staging files for {slug}: {e}")
                # Don't fail the whole operation for cleanup issues

        logger.info(f"Successfully added {len(new_entries)} new entries")
    else:
        logger.error("Failed to append entries, staging files preserved")

    return success, processed_slugs

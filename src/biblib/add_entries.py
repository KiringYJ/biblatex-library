"""Add new bibliography entries from staging files."""

import json
import logging
import re
import tempfile
from pathlib import Path

import bibtexparser
import msgspec
from bibtexparser.model import Entry

from .config import WorkspaceConfig
from .exceptions import BackupError, FileOperationError, InvalidDataError
from .generate import generate_labels
from .types import (
    AddOrderList,
    IdentifierCollection,
    IdentifierData,
    KeyMapping,
)
from .validate import extract_citekeys_from_bib, extract_citekeys_from_identifier_collection

logger = logging.getLogger(__name__)


def create_backup(workspace: Path) -> str:
    """Create timestamped backup of core data files.

    Args:
        workspace: Path to the workspace directory

    Returns:
        Backup directory path

    Raises:
        BackupError: If backup creation fails
    """
    import datetime

    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = workspace / "staging" / f"backup-{timestamp}"
    config = WorkspaceConfig.from_workspace(workspace)

    try:
        backup_dir.mkdir(parents=True, exist_ok=True)

        # Copy core data files using config
        if config.bib_path.exists():
            backup_dir.joinpath("library.bib").write_bytes(config.bib_path.read_bytes())
        if config.identifier_path.exists():
            backup_dir.joinpath("identifier_collection.json").write_bytes(
                config.identifier_path.read_bytes()
            )
        if config.add_order_path.exists():
            backup_dir.joinpath("add_order.json").write_bytes(config.add_order_path.read_bytes())

        logger.info(f"Backup created at {backup_dir}")
        return str(backup_dir)

    except OSError as e:
        raise BackupError(f"Failed to create backup at {backup_dir}: {e}") from e


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


def load_existing_keys(config: WorkspaceConfig) -> set[str]:
    """Load all existing citekeys from the three data files.

    Args:
        config: Workspace configuration with file paths

    Returns:
        Set of all existing citekeys
    """
    existing_keys: set[str] = set()

    try:
        if config.bib_path.exists():
            existing_keys.update(extract_citekeys_from_bib(config.bib_path))
    except OSError as e:
        raise FileOperationError(f"Failed to load keys from {config.bib_path}: {e}") from e
    except Exception as e:
        # Catch bibtexparser errors without knowing their exact type
        raise InvalidDataError(f"Failed to parse bib file {config.bib_path}: {e}") from e

    try:
        if config.identifier_path.exists():
            existing_keys.update(
                extract_citekeys_from_identifier_collection(config.identifier_path)
            )
    except (OSError, msgspec.DecodeError, msgspec.ValidationError) as e:
        raise InvalidDataError(f"Failed to load keys from {config.identifier_path}: {e}") from e

    try:
        if config.add_order_path.exists():
            with open(config.add_order_path, encoding="utf-8") as f:
                raw_data = json.load(f)
                add_order_data = msgspec.convert(raw_data, type=list[str])
                existing_keys.update(add_order_data)  # No need for str() on strings!
    except (OSError, json.JSONDecodeError) as e:
        raise FileOperationError(f"Failed to load keys from {config.add_order_path}: {e}") from e
    except msgspec.ValidationError as e:
        raise InvalidDataError(f"Invalid add_order data in {config.add_order_path}: {e}") from e

    logger.debug(f"Loaded {len(existing_keys)} existing keys")
    return existing_keys


def process_staging_entry(
    slug: str, bib_path: Path, json_path: Path, existing_keys: set[str]
) -> tuple[KeyMapping, dict[str, Entry], dict[str, IdentifierData]] | None:
    """Process a staging entry pair (can contain multiple entries).

    Args:
        slug: The staging file slug (filename without extension)
        bib_path: Path to the .bib file
        json_path: Path to the .json file
        existing_keys: Set of existing citekeys to check for duplicates

    Returns:
        Tuple of (key_mapping, entry_data, identifier_data) if successful, None if skipped
        - key_mapping: dict mapping original keys to new generated keys
        - entry_data: dict of all processed entries with new keys
        - identifier_data: dict of all identifier data with new keys
    """
    logger.info(f"Processing staging entry: {slug}")

    try:
        # Parse the bib file and extract entry data
        logger.debug(f"Parsing bib file: {bib_path}")
        lib = bibtexparser.parse_file(str(bib_path))

        if lib.failed_blocks:
            logger.error(f"Failed to parse {bib_path}: {len(lib.failed_blocks)} failed blocks")
            return None

        if len(lib.entries) == 0:
            logger.error(f"No entries found in {bib_path}")
            return None

        logger.info(f"Found {len(lib.entries)} entries in {bib_path}")

        # Load identifier data
        logger.debug(f"Loading identifier data: {json_path}")
        with open(json_path, encoding="utf-8") as f:
            raw_data = json.load(f)
            identifier_data = msgspec.convert(raw_data, type=dict[str, IdentifierData])

        # Initialize result containers
        key_mapping: KeyMapping = {}
        all_entry_data: dict[str, Entry] = {}
        all_identifier_data: dict[str, IdentifierData] = {}

        # Process each entry in the file
        for entry in lib.entries:
            original_key = entry.key

            if original_key not in identifier_data:
                logger.error(f"Entry key '{original_key}' not found in identifier data")
                continue

            # Extract the identifier data for this specific entry
            entry_identifier_data: IdentifierData = identifier_data[original_key]

            # Generate new label for this entry
            new_key = process_single_entry(
                entry,
                entry_identifier_data,
                existing_keys,
                original_key,
            )
            if new_key is None:
                logger.error(f"Failed to generate label for entry {original_key}")
                continue

            # Store the mapping and data
            key_mapping[original_key] = new_key
            all_entry_data[new_key] = entry
            all_identifier_data[new_key] = entry_identifier_data
            existing_keys.add(new_key)  # Prevent duplicates within this batch

        if not key_mapping:
            logger.error(f"No entries were successfully processed from {slug}")
            return None

        logger.info(f"Successfully processed {len(key_mapping)} entries from {slug}")
        return key_mapping, all_entry_data, all_identifier_data

    except (OSError, json.JSONDecodeError) as e:
        raise FileOperationError(f"Failed to read staging files for {slug}: {e}") from e
    except (msgspec.DecodeError, msgspec.ValidationError) as e:
        raise InvalidDataError(f"Invalid data format in staging files for {slug}: {e}") from e


def process_single_entry(
    entry: Entry,
    entry_identifier_data: IdentifierData,
    existing_keys: set[str],
    original_key: str,
) -> str | None:
    """Process a single entry and generate its new key.

    Args:
        entry: The bibtex entry to process
        entry_identifier_data: The identifier data for this entry
        existing_keys: Set of existing keys to avoid duplicates
        original_key: Original key of the entry

    Returns:
        New generated key if successful, None otherwise
    """
    try:
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
            json.dump({original_key: entry_identifier_data}, temp_json, indent=2)
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
            logger.warning(f"Skipping duplicate key: {new_key}")
            return None

        logger.info(f"Generated new key: {original_key} -> {new_key}")

        # Update entry with new key
        entry.key = new_key

        return new_key

    except Exception as e:
        # Keep this as Exception since generate_labels can have various errors
        logger.error(f"Error processing entry {original_key}: {e}")
        return None


def _load_existing_data(
    bib_path: Path, identifier_path: Path, add_order_path: Path
) -> tuple[bibtexparser.Library, IdentifierCollection, AddOrderList]:
    """Load existing data from the three data files.

    Args:
        bib_path: Path to library.bib
        identifier_path: Path to identifier_collection.json
        add_order_path: Path to add_order.json

    Returns:
        Tuple of (library, identifier_collection, add_order)
    """
    # Load library
    if bib_path.exists():
        library = bibtexparser.parse_file(str(bib_path))
    else:
        library = bibtexparser.Library()

    # Load identifier collection
    identifier_collection: IdentifierCollection = {}
    if identifier_path.exists():
        with open(identifier_path, encoding="utf-8") as f:
            raw_data = json.load(f)
            identifier_collection = msgspec.convert(raw_data, type=dict[str, IdentifierData])

    # Load add order
    add_order: AddOrderList = []
    if add_order_path.exists():
        with open(add_order_path, encoding="utf-8") as f:
            raw_data = json.load(f)
            add_order = msgspec.convert(raw_data, type=list[str])

    return library, identifier_collection, add_order


def _add_entries_to_data(
    new_entries: list[tuple[str, dict[str, Entry], dict[str, IdentifierData]]],
    library: bibtexparser.Library,
    identifier_collection: IdentifierCollection,
    add_order: AddOrderList,
) -> None:
    """Add new entries to the data structures.

    Args:
        new_entries: List of (key, entry_data, identifier_data) tuples
        library: Library to add entries to
        identifier_collection: Identifier collection to update
        add_order: Add order list to append to
    """
    for new_key, entry_data, identifier_data in new_entries:
        logger.debug(f"Processing entry: {new_key}")

        # Add to library
        for entry_key, entry in entry_data.items():
            logger.debug(f"Adding entry {entry_key} of type {type(entry)}")
            library.add(entry)  # Use library.add() instead of library.entries.append()

        # Add to identifier collection
        identifier_collection.update(identifier_data)

        # Add to add_order
        add_order.append(new_key)

        logger.debug(f"Added entry: {new_key}")


def _write_data_files(
    library: bibtexparser.Library,
    identifier_collection: IdentifierCollection,
    add_order: AddOrderList,
    bib_path: Path,
    identifier_path: Path,
    add_order_path: Path,
) -> None:
    """Write data structures back to files.

    Args:
        library: Library to write
        identifier_collection: Identifier collection to write
        add_order: Add order list to write
        bib_path: Path to library.bib
        identifier_path: Path to identifier_collection.json
        add_order_path: Path to add_order.json
    """
    # Write back to files with UTF-8 encoding
    bib_string = bibtexparser.write_string(library)
    with open(bib_path, "w", encoding="utf-8") as f:
        f.write(bib_string)

    with open(identifier_path, "w", encoding="utf-8") as f:
        json.dump(identifier_collection, f, indent=2, ensure_ascii=False)

    with open(add_order_path, "w", encoding="utf-8") as f:
        json.dump(add_order, f, indent=2, ensure_ascii=False)


def append_to_files(
    new_entries: list[tuple[str, dict[str, Entry], dict[str, IdentifierData]]],
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
    except BackupError as e:
        logger.error(f"✗ Backup failed: {e}")
        return False

    try:
        # Load existing data
        library, identifier_collection, add_order = _load_existing_data(
            bib_path, identifier_path, add_order_path
        )

        # Add new entries to data structures
        _add_entries_to_data(new_entries, library, identifier_collection, add_order)

        # Write data back to files
        _write_data_files(
            library, identifier_collection, add_order, bib_path, identifier_path, add_order_path
        )

        logger.info(f"Successfully appended {len(new_entries)} entries")
        return True

    except OSError as e:
        raise FileOperationError(f"Failed to write files: {e}") from e
    except Exception as e:
        # Keep Exception for bibtexparser write errors
        raise FileOperationError(f"Failed to append entries: {e}") from e


def cleanup_processed_files(config: WorkspaceConfig, processed_slugs: list[str]) -> None:
    """Delete processed staging files after successful addition.

    Args:
        config: Workspace configuration
        processed_slugs: List of slugs to clean up
    """
    for slug in processed_slugs:
        bib_file = config.staging_dir / f"{slug}.bib"
        json_file = config.staging_dir / f"{slug}.json"

        try:
            bib_file.unlink()
            json_file.unlink()
            logger.info(f"Deleted processed staging files: {slug}")
        except OSError as e:
            logger.error(f"Failed to delete staging files for {slug}: {e}")
            # Don't fail the whole operation for cleanup issues


def process_staging_pairs(
    pairs: list[tuple[str, Path, Path]], existing_keys: set[str]
) -> tuple[list[tuple[str, dict[str, Entry], dict[str, IdentifierData]]], list[str]]:
    """Process all staging pairs and collect new entries.

    Args:
        pairs: List of (slug, bib_path, json_path) tuples
        existing_keys: Set of existing citekeys to check against

    Returns:
        Tuple of (new_entries, processed_slugs)
    """
    new_entries: list[tuple[str, dict[str, Entry], dict[str, IdentifierData]]] = []
    processed_slugs: list[str] = []

    for slug, bib_file, json_file in pairs:
        result = process_staging_entry(slug, bib_file, json_file, existing_keys)
        if result is not None:
            key_mapping, entry_data, identifier_data = result

            # Convert to the format expected by append_to_files
            for _original_key, new_key in key_mapping.items():
                new_entries.append(
                    (new_key, {new_key: entry_data[new_key]}, {new_key: identifier_data[new_key]})
                )
                existing_keys.add(new_key)  # Prevent duplicates within the batch

            processed_slugs.append(slug)
            logger.info(f"Processed {len(key_mapping)} entries from {slug}")
        else:
            logger.warning(f"Skipped staging pair: {slug}")

    return new_entries, processed_slugs


def add_entries_from_staging(workspace: Path) -> tuple[bool, list[str]]:
    """Add new entries from staging directory to the main data files.

    Args:
        workspace: Path to the workspace root

    Returns:
        Tuple of (success, list_of_processed_slugs)
    """
    logger.info("Starting add entries from staging workflow")

    # Create configuration
    config = WorkspaceConfig.from_workspace(workspace)

    # Find staging pairs
    pairs = find_staging_pairs(config.staging_dir)
    if not pairs:
        logger.info("No staging pairs found")
        return True, []

    # Load existing keys and process staging pairs
    existing_keys = load_existing_keys(config)
    new_entries, processed_slugs = process_staging_pairs(pairs, existing_keys)

    if not new_entries:
        logger.info("No new entries to add")
        return True, []

    # Append to data files
    success = append_to_files(
        new_entries, config.bib_path, config.identifier_path, config.add_order_path
    )

    if success:
        cleanup_processed_files(config, processed_slugs)
        logger.info(f"Successfully added {len(new_entries)} new entries")
    else:
        logger.error("Failed to append entries, staging files preserved")

    return success, processed_slugs

"""Validation module for biblatex library consistency checks."""

import json
import logging
import re
from pathlib import Path

import bibtexparser
import msgspec

from .types import IdentifierCollection, IdentifierData

logger = logging.getLogger(__name__)


def extract_citekeys_from_bib(bib_path: Path) -> set[str]:
    """Extract all citekeys from a .bib file using bibtexparser v2.

    Args:
        bib_path: Path to the .bib file

    Returns:
        Set of citekeys found in the file

    Raises:
        FileNotFoundError: If bib file doesn't exist
        ValueError: If parsing fails
    """
    if not bib_path.exists():
        raise FileNotFoundError(f"Bibliography file not found: {bib_path}")

    logger.debug(f"Parsing .bib file: {bib_path}")

    try:
        lib = bibtexparser.parse_file(str(bib_path))

        if lib.failed_blocks:
            failed_keys = [str(block) for block in lib.failed_blocks]
            raise ValueError(f"Failed to parse {len(lib.failed_blocks)} blocks: {failed_keys}")

        citekeys = {entry.key for entry in lib.entries}
        logger.debug(f"Found {len(citekeys)} citekeys in {bib_path.name}")

        return citekeys

    except Exception as e:
        raise ValueError(f"Failed to parse {bib_path}: {e}") from e


def extract_citekeys_from_add_order(add_order_path: Path) -> set[str]:
    """Extract citekeys from add_order.json.

    Args:
        add_order_path: Path to add_order.json

    Returns:
        Set of citekeys from the order array

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If JSON is invalid or format is wrong
    """
    if not add_order_path.exists():
        raise FileNotFoundError(f"Add order file not found: {add_order_path}")

    logger.debug(f"Reading add order file: {add_order_path}")

    try:
        with open(add_order_path, encoding="utf-8") as f:
            data = json.load(f)

        # Use msgspec for direct type-safe validation
        data_list = msgspec.convert(data, type=list[str])
        citekeys = set(data_list)
        logger.debug(f"Found {len(citekeys)} citekeys in {add_order_path.name}")

        return citekeys

    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in {add_order_path}: {e}") from e


def extract_citekeys_from_identifier_collection(identifier_path: Path) -> set[str]:
    """Extract citekeys from identifier_collection.json.

    Args:
        identifier_path: Path to identifier_collection.json

    Returns:
        Set of citekeys (top-level keys in the JSON object)

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If JSON is invalid or format is wrong
    """
    if not identifier_path.exists():
        raise FileNotFoundError(f"Identifier collection file not found: {identifier_path}")

    logger.debug(f"Reading identifier collection file: {identifier_path}")

    try:
        with open(identifier_path, encoding="utf-8") as f:
            data = json.load(f)

        # Use msgspec for direct type-safe validation
        data_dict = msgspec.convert(data, type=dict[str, IdentifierData])
        citekeys = set(data_dict.keys())
        logger.debug(f"Found {len(citekeys)} citekeys in {identifier_path.name}")

        return citekeys

    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in {identifier_path}: {e}") from e


def validate_citekey_consistency(
    bib_path: Path, add_order_path: Path, identifier_path: Path
) -> bool:
    """Validate that all three data sources contain the same citekeys.

    Args:
        bib_path: Path to library.bib
        add_order_path: Path to add_order.json
        identifier_path: Path to identifier_collection.json

    Returns:
        True if all citekeys are consistent across sources

    Raises:
        FileNotFoundError: If any required file is missing
        ValueError: If parsing any file fails
    """
    logger.info("Validating citekey consistency across data sources")

    # Extract citekeys from each source
    bib_keys = extract_citekeys_from_bib(bib_path)
    order_keys = extract_citekeys_from_add_order(add_order_path)
    identifier_keys = extract_citekeys_from_identifier_collection(identifier_path)

    # Check for consistency
    all_consistent = True

    # Find keys missing from each source
    missing_from_bib = (order_keys | identifier_keys) - bib_keys
    missing_from_order = (bib_keys | identifier_keys) - order_keys
    missing_from_identifiers = (bib_keys | order_keys) - identifier_keys

    # Find keys only in specific sources
    only_in_bib = bib_keys - (order_keys | identifier_keys)
    only_in_order = order_keys - (bib_keys | identifier_keys)
    only_in_identifiers = identifier_keys - (bib_keys | order_keys)

    # Report inconsistencies
    if missing_from_bib:
        logger.error(f"Missing from library.bib: {sorted(missing_from_bib)}")
        all_consistent = False

    if missing_from_order:
        logger.error(f"Missing from add_order.json: {sorted(missing_from_order)}")
        all_consistent = False

    if missing_from_identifiers:
        logger.error(f"Missing from identifier_collection.json: {sorted(missing_from_identifiers)}")
        all_consistent = False

    if only_in_bib:
        logger.error(f"Only in library.bib: {sorted(only_in_bib)}")
        all_consistent = False

    if only_in_order:
        logger.error(f"Only in add_order.json: {sorted(only_in_order)}")
        all_consistent = False

    if only_in_identifiers:
        logger.error(f"Only in identifier_collection.json: {sorted(only_in_identifiers)}")
        all_consistent = False

    if all_consistent:
        total_keys = len(bib_keys)
        logger.info(f"✓ All {total_keys} citekeys are consistent across data sources")
    else:
        logger.error("✗ Citekey inconsistencies found across data sources")

    return all_consistent


def validate_citekey_labels(bib_path: Path, identifier_path: Path) -> bool:
    """Validate that existing citekeys match their generated labels.

    Args:
        bib_path: Path to library.bib
        identifier_path: Path to identifier_collection.json

    Returns:
        True if all citekeys match their generated labels

    Raises:
        FileNotFoundError: If any required file is missing
        ValueError: If parsing any file fails
    """
    logger.info("Validating that citekeys match generated labels")

    # Import here to avoid circular imports
    from biblib.generate import generate_labels

    try:
        # Generate what the labels should be
        generated_labels = generate_labels(bib_path, identifier_path)

        # Check each entry
        mismatches: list[tuple[str, str]] = []
        matches = 0

        for current_key, expected_label in generated_labels.items():
            if current_key == expected_label:
                matches += 1
                logger.debug(f"✓ {current_key} matches generated label")
            else:
                mismatches.append((current_key, expected_label))
                logger.warning(f"✗ {current_key} should be {expected_label}")

        # Report results
        total_entries = len(generated_labels)
        if mismatches:
            logger.error(
                f"✗ Found {len(mismatches)} citekey mismatches out of {total_entries} entries:"
            )
            for current, expected in mismatches:
                logger.error(f"  {current} → should be → {expected}")
            return False
        else:
            logger.info(f"✓ All {matches} citekeys match their generated labels")
            return True

    except Exception as e:
        logger.error(f"Failed to validate citekey labels: {e}")
        return False


def fix_citekey_labels(bib_path: Path, add_order_path: Path, identifier_path: Path) -> bool:
    """Fix citekeys by replacing them with their correct generated labels.

    Args:
        bib_path: Path to library.bib
        add_order_path: Path to add_order.json
        identifier_path: Path to identifier_collection.json

    Returns:
        True if fixes were applied successfully

    Raises:
        FileNotFoundError: If any required file is missing
        ValueError: If parsing any file fails
    """
    logger.info("Fixing citekeys to match generated labels")

    # Import here to avoid circular imports
    from biblib.generate import generate_labels

    try:
        # Generate what the labels should be
        generated_labels = generate_labels(bib_path, identifier_path)

        # Find mismatches
        mismatches: list[tuple[str, str]] = []
        for current_key, expected_label in generated_labels.items():
            if current_key != expected_label:
                mismatches.append((current_key, expected_label))

        if not mismatches:
            logger.info("✓ All citekeys already match their generated labels")
            return True

        logger.info("Found %d citekey mismatches to fix", len(mismatches))

        # Create mapping for replacements
        replacement_map = dict(mismatches)

        # Fix library.bib file
        logger.info("Fixing citekeys in %s", bib_path.name)
        _fix_bib_file(bib_path, replacement_map)

        # Fix add_order.json file
        logger.info("Fixing citekeys in %s", add_order_path.name)
        _fix_add_order_file(add_order_path, replacement_map)

        # Fix identifier_collection.json file
        logger.info("Fixing citekeys in %s", identifier_path.name)
        _fix_identifier_collection_file(identifier_path, replacement_map)

        # Report what was fixed
        for old_key, new_key in mismatches:
            logger.info("✓ Fixed: %s → %s", old_key, new_key)

        logger.info("✓ Successfully fixed %d citekeys", len(mismatches))
        return True

    except Exception as e:
        logger.error("Failed to fix citekey labels: %s", e)
        return False


def _fix_bib_file(bib_path: Path, replacement_map: dict[str, str]) -> None:
    """Fix citekeys in the .bib file.

    Args:
        bib_path: Path to the .bib file
        replacement_map: Dictionary mapping old citekeys to new ones
    """
    # Read the file content
    with open(bib_path, encoding="utf-8") as f:
        content = f.read()

    # Replace citekeys in entry declarations
    for old_key, new_key in replacement_map.items():
        # Pattern to match @entrytype{oldkey, (with word boundaries)
        pattern = rf"(@[a-zA-Z]+\s*\{{\s*){re.escape(old_key)}(\s*,)"
        replacement = rf"\1{new_key}\2"
        content = re.sub(pattern, replacement, content)

    # Write back the modified content
    with open(bib_path, "w", encoding="utf-8") as f:
        f.write(content)


def _fix_add_order_file(add_order_path: Path, replacement_map: dict[str, str]) -> None:
    """Fix citekeys in the add_order.json file.

    Args:
        add_order_path: Path to add_order.json
        replacement_map: Dictionary mapping old citekeys to new ones
    """
    # Load the JSON data
    with open(add_order_path, encoding="utf-8") as f:
        data = json.load(f)

    # Replace citekeys in the list
    if isinstance(data, list):
        data_list = msgspec.convert(data, type=list[str])
        for i, key in enumerate(data_list):
            if key in replacement_map:
                data_list[i] = replacement_map[key]

        # Write back the modified data
        with open(add_order_path, "w", encoding="utf-8") as f:
            json.dump(data_list, f, indent=2, ensure_ascii=False)
    else:
        raise ValueError(f"Expected list in {add_order_path}, got {type(data).__name__}")


def _fix_identifier_collection_file(identifier_path: Path, replacement_map: dict[str, str]) -> None:
    """Fix citekeys in the identifier_collection.json file.

    Args:
        identifier_path: Path to identifier_collection.json
        replacement_map: Dictionary mapping old citekeys to new ones
    """
    # Load the JSON data
    with open(identifier_path, encoding="utf-8") as f:
        data = json.load(f)

    # Replace keys in the dictionary
    if isinstance(data, dict):
        data_dict = msgspec.convert(data, type=dict[str, IdentifierData])
        new_data: IdentifierCollection = {}
        for old_key, value in data_dict.items():
            new_key = replacement_map.get(old_key, old_key)
            new_data[new_key] = value

        # Write back the modified data
        with open(identifier_path, "w", encoding="utf-8") as f:
            json.dump(new_data, f, indent=2, ensure_ascii=False)
    else:
        raise ValueError(f"Expected dict in {identifier_path}, got {type(data).__name__}")

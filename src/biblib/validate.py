"""Validation module for biblatex library consistency checks."""

import json
import logging
from pathlib import Path
from typing import Any, cast

import bibtexparser  # type: ignore[import-untyped]

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

    logger.debug("Parsing .bib file: %s", bib_path)

    try:
        lib = bibtexparser.parse_file(str(bib_path))  # type: ignore[attr-defined]

        if lib.failed_blocks:  # type: ignore[attr-defined]
            failed_keys = [str(block) for block in lib.failed_blocks]  # type: ignore[attr-defined]
            raise ValueError(f"Failed to parse {len(lib.failed_blocks)} blocks: {failed_keys}")  # type: ignore[attr-defined]

        citekeys = {entry.key for entry in lib.entries}  # type: ignore[attr-defined]
        logger.debug("Found %d citekeys in %s", len(citekeys), bib_path.name)

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

    logger.debug("Reading add order file: %s", add_order_path)

    try:
        with open(add_order_path, encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, list):
            raise ValueError(f"Expected array, got {type(data).__name__}")

        # Convert to set, ensuring all items are strings
        data_list = cast(list[Any], data)
        citekeys = {str(item) for item in data_list}
        logger.debug("Found %d citekeys in %s", len(citekeys), add_order_path.name)

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

    logger.debug("Reading identifier collection file: %s", identifier_path)

    try:
        with open(identifier_path, encoding="utf-8") as f:
            data: Any = json.load(f)

        if not isinstance(data, dict):
            raise ValueError(f"Expected object, got {type(data).__name__}")

        # Convert keys to set of strings
        data_dict = cast(dict[str, Any], data)
        citekeys = {str(key) for key in data_dict.keys()}
        logger.debug("Found %d citekeys in %s", len(citekeys), identifier_path.name)

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
        logger.error("Missing from library.bib: %s", sorted(missing_from_bib))
        all_consistent = False

    if missing_from_order:
        logger.error("Missing from add_order.json: %s", sorted(missing_from_order))
        all_consistent = False

    if missing_from_identifiers:
        logger.error(
            "Missing from identifier_collection.json: %s", sorted(missing_from_identifiers)
        )
        all_consistent = False

    if only_in_bib:
        logger.error("Only in library.bib: %s", sorted(only_in_bib))
        all_consistent = False

    if only_in_order:
        logger.error("Only in add_order.json: %s", sorted(only_in_order))
        all_consistent = False

    if only_in_identifiers:
        logger.error("Only in identifier_collection.json: %s", sorted(only_in_identifiers))
        all_consistent = False

    if all_consistent:
        total_keys = len(bib_keys)
        logger.info("✓ All %d citekeys are consistent across data sources", total_keys)
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
                logger.debug("✓ %s matches generated label", current_key)
            else:
                mismatches.append((current_key, expected_label))
                logger.warning("✗ %s should be %s", current_key, expected_label)

        # Report results
        total_entries = len(generated_labels)
        if mismatches:
            logger.error(
                "✗ Found %d citekey mismatches out of %d entries:", len(mismatches), total_entries
            )
            for current, expected in mismatches:
                logger.error("  %s → should be → %s", current, expected)
            return False
        else:
            logger.info("✓ All %d citekeys match their generated labels", matches)
            return True

    except Exception as e:
        logger.error("Failed to validate citekey labels: %s", e)
        return False

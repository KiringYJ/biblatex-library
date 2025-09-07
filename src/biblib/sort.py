"""Sorting functionality for bibliographic database files."""

import json
import logging
from pathlib import Path

import bibtexparser
from bibtexparser.library import Block
from bibtexparser.model import Entry

from .json_validation import validate_add_order_list, validate_identifier_collection
from .types import IdentifierCollection

logger = logging.getLogger(__name__)


def sort_alphabetically(library_path: Path, identifier_path: Path, add_order_path: Path) -> None:
    """Sort library.bib and identifier_collection.json alphabetically by citekey.

    This reads add_order.json to get the list of citekeys, sorts them alphabetically,
    then sorts the other two files to match. add_order.json itself is never modified.

    Args:
        library_path: Path to library.bib file
        identifier_path: Path to identifier_collection.json file
        add_order_path: Path to add_order.json file (read-only)
    """
    logger.info("Sorting files alphabetically by citekey")

    # Load add_order.json to get citekey list (read-only)
    with open(add_order_path, encoding="utf-8") as f:
        citekeys_data = json.load(f)

    # Use proper validation function to eliminate type warnings
    citekeys = validate_add_order_list(citekeys_data)

    # Sort citekeys alphabetically
    sorted_citekeys = sorted(citekeys)

    # Sort library.bib entries
    _sort_library_bib(library_path, sorted_citekeys)

    # Sort identifier_collection.json entries
    _sort_identifier_collection(identifier_path, sorted_citekeys)

    logger.info("✓ Successfully sorted files alphabetically by citekey")


def sort_by_add_order(library_path: Path, identifier_path: Path, add_order_path: Path) -> None:
    """Sort library.bib and identifier_collection.json to match add_order.json sequence.

    This sorts the files to match the exact order specified in add_order.json.
    add_order.json itself is never modified.

    Args:
        library_path: Path to library.bib file
        identifier_path: Path to identifier_collection.json file
        add_order_path: Path to add_order.json file (read-only)
    """
    logger.info("Sorting files to match add_order.json sequence")

    # Load add_order.json to get desired order (read-only)
    with open(add_order_path, encoding="utf-8") as f:
        citekey_order_data = json.load(f)

    # Use proper validation function to eliminate type warnings
    citekey_order = validate_add_order_list(citekey_order_data)

    # Sort library.bib entries
    _sort_library_bib(library_path, citekey_order)

    # Sort identifier_collection.json entries
    _sort_identifier_collection(identifier_path, citekey_order)

    logger.info("✓ Successfully sorted files to match add_order.json sequence")


def _sort_library_bib(library_path: Path, citekey_order: list[str]) -> None:
    """Sort library.bib entries according to the specified citekey order.

    Args:
        library_path: Path to library.bib file
        citekey_order: List of citekeys in desired order
    """
    # Parse the .bib file
    library = bibtexparser.parse_file(str(library_path))

    # Create a mapping from citekey to entry for efficient lookup
    entry_map: dict[str, Entry] = {entry.key: entry for entry in library.entries}

    # Build sorted entries list based on citekey_order
    sorted_entries: list[Entry] = []
    missing_entries: list[Entry] = []

    for citekey in citekey_order:
        if citekey in entry_map:
            sorted_entries.append(entry_map[citekey])
        else:
            logger.warning(f"Citekey '{citekey}' not found in library.bib")

    # Add any entries that weren't in the order list (shouldn't happen in well-maintained data)
    for entry in library.entries:
        if entry.key not in citekey_order:
            missing_entries.append(entry)
            logger.warning(f"Entry '{entry.key}' found in library.bib but not in citekey order")

    # Create a new library with the sorted entries and other blocks
    sorted_blocks: list[Block] = []

    # Add non-entry blocks (comments, preambles, strings) first
    for block in library.blocks:
        if block not in library.entries:
            sorted_blocks.append(block)

    # Add sorted entries
    sorted_blocks.extend(sorted_entries + missing_entries)

    # Create new library with sorted blocks
    new_library = bibtexparser.Library(sorted_blocks)

    # Write back to file with explicit UTF-8 encoding
    bibtex_str = bibtexparser.write_string(new_library)
    with open(library_path, "w", encoding="utf-8") as f:
        f.write(str(bibtex_str))  # Ensure we write a string

    logger.info(f"Updated {library_path} with {len(sorted_entries)} sorted entries")


def _sort_identifier_collection(identifier_path: Path, citekey_order: list[str]) -> None:
    """Sort identifier_collection.json according to the specified citekey order.

    Args:
        identifier_path: Path to identifier_collection.json file
        citekey_order: List of citekeys in desired order
    """
    # Load identifier collection
    with open(identifier_path, encoding="utf-8") as f:
        data_raw = json.load(f)

    # Use proper validation function to eliminate type warnings
    data = validate_identifier_collection(data_raw)

    # Create ordered dictionary based on citekey_order
    sorted_data: IdentifierCollection = {}
    missing_keys: list[str] = []

    for citekey in citekey_order:
        if citekey in data:
            sorted_data[citekey] = data[citekey]
        else:
            logger.warning(f"Citekey '{citekey}' not found in identifier_collection.json")

    # Add any keys that weren't in the order list (shouldn't happen in well-maintained data)
    for key in data:
        if key not in citekey_order:
            missing_keys.append(key)
            sorted_data[key] = data[key]
            logger.warning(
                f"Key '{key}' found in identifier_collection.json but not in citekey order"
            )

    # Write back to file
    with open(identifier_path, "w", encoding="utf-8") as f:
        json.dump(sorted_data, f, indent=2)

    logger.info(f"Updated {identifier_path} with {len(sorted_data)} sorted entries")

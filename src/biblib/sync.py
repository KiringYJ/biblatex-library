"""Synchronization utilities for updating library.bib from identifier collection."""

import json
import logging
import re
from pathlib import Path

import bibtexparser as btp
from bibtexparser.library import Library
from bibtexparser.model import Entry

from .types import IdentifierCollection


def load_identifier_collection(identifier_path: Path) -> IdentifierCollection:
    """Load identifier collection data from JSON file.

    Args:
        identifier_path: Path to identifier_collection.json

    Returns:
        Dictionary mapping citekeys to identifier data

    Raises:
        FileNotFoundError: If identifier file doesn't exist
        ValueError: If JSON is invalid
    """
    logger = logging.getLogger(__name__)

    try:
        with open(identifier_path, encoding="utf-8") as f:
            data = json.load(f)
        logger.debug(f"Loaded {len(data)} entries from identifier collection")
        return data
    except FileNotFoundError as e:
        raise FileNotFoundError(f"Identifier collection not found: {identifier_path}") from e
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in identifier collection: {e}") from e


def load_bibtex_library(bib_path: Path) -> tuple[Library, dict[str, Entry]]:
    """Load bibtex library and create citekey mapping.

    Args:
        bib_path: Path to library.bib file

    Returns:
        Tuple of (library object, citekey->entry mapping)

    Raises:
        FileNotFoundError: If bib file doesn't exist
        ValueError: If bibtex parsing fails
    """
    logger = logging.getLogger(__name__)

    try:
        library = btp.parse_file(str(bib_path))

        # Create mapping from citekey to entry for easy lookup
        entry_map = {entry.key: entry for entry in library.entries}

        logger.debug(f"Loaded {len(entry_map)} entries from bibtex library")
        return library, entry_map
    except FileNotFoundError as e:
        raise FileNotFoundError(f"Library file not found: {bib_path}") from e
    except Exception as e:
        raise ValueError(f"Failed to parse bibtex library: {e}") from e


def sync_identifiers_to_library(
    bib_path: Path,
    identifier_path: Path,
    dry_run: bool = False,
    fields_to_sync: set[str] | None = None,
) -> tuple[bool, list[str]]:
    """Sync identifier data back to library.bib file.

    Updates fields in library.bib based on authoritative data from identifier_collection.json.
    The identifier collection is considered the source of truth for identifier fields.

    Args:
        bib_path: Path to library.bib file
        identifier_path: Path to identifier_collection.json
        dry_run: If True, only report changes without making them
        fields_to_sync: Set of field names to sync (None = sync all supported fields)

    Returns:
        Tuple of (success, list of change descriptions)

    Raises:
        FileNotFoundError: If input files don't exist
        ValueError: If parsing fails
    """
    logger = logging.getLogger(__name__)

    # Default fields that can be synced from identifier collection to bibtex
    default_sync_fields = {"isbn", "doi", "url", "eprint", "mrnumber", "zbl"}
    if fields_to_sync is None:
        fields_to_sync = default_sync_fields

    logger.info(f"Starting identifier sync {('(dry run)' if dry_run else '')}")
    logger.debug(f"Fields to sync: {', '.join(sorted(fields_to_sync))}")

    # Load data
    identifier_data = load_identifier_collection(identifier_path)
    library, entry_map = load_bibtex_library(bib_path)

    changes: list[str] = []
    entries_modified = 0

    # Process each entry in identifier collection
    for citekey, id_info in identifier_data.items():
        if citekey not in entry_map:
            logger.warning(f"Entry {citekey} in identifier collection not found in library")
            continue

        entry = entry_map[citekey]
        identifiers = id_info.get("identifiers", {})

        # Check each identifier field that we can sync
        for id_field_raw, id_value_raw in identifiers.items():
            # Now we know these are strings from our TypedDict
            id_field: str = id_field_raw
            id_value: str = id_value_raw

            # Map identifier collection field names to bibtex field names
            bibtex_field = _map_identifier_to_bibtex_field(id_field)

            if bibtex_field not in fields_to_sync:
                continue

            current_value = _get_field_value(entry, bibtex_field)
            normalized_id_value = _normalize_field_value(bibtex_field, id_value, id_field)

            # Check if we need to update
            if _field_needs_update(bibtex_field, current_value, normalized_id_value):
                change_desc = (
                    f"{citekey}: {bibtex_field} '{current_value}' -> '{normalized_id_value}'"
                )
                changes.append(change_desc)
                logger.info(f"  {change_desc}")

                if not dry_run:
                    _set_field_value(entry, bibtex_field, normalized_id_value)
                    entries_modified += 1  # Save changes if not dry run
    if not dry_run and entries_modified > 0:
        try:
            # Write with explicit UTF-8 encoding to handle Unicode characters
            bibtex_string = btp.write_string(library)
            with open(bib_path, "w", encoding="utf-8") as f:
                f.write(bibtex_string)
            logger.info(f"✓ Updated {entries_modified} entries in {bib_path}")
        except Exception as e:
            logger.error(f"Failed to write updated library: {e}")
            return False, changes

    if dry_run:
        logger.info(f"✓ Dry run complete: {len(changes)} potential changes identified")
    else:
        logger.info(f"✓ Sync complete: {len(changes)} changes applied")

    return True, changes


def _get_field_value(entry: Entry, field_name: str) -> str | None:
    """Get field value from bibtex entry.

    Args:
        entry: Bibtex entry
        field_name: Name of field to get

    Returns:
        Field value as string, or None if field doesn't exist
    """
    field = entry.fields_dict.get(field_name)
    if field is None:
        return None
    return str(field.value)


def _set_field_value(entry: Entry, field_name: str, value: str) -> None:
    """Set field value in bibtex entry.

    Args:
        entry: Bibtex entry to modify
        field_name: Name of field to set
        value: Value to set
    """
    from bibtexparser.model import Field

    # Check if field already exists
    if field_name in entry.fields_dict:
        # Update existing field
        entry.fields_dict[field_name].value = value
    else:
        # Add new field
        new_field = Field(value=value)
        entry.fields_dict[field_name] = new_field


def _map_identifier_to_bibtex_field(identifier_field: str) -> str:
    """Map identifier collection field names to bibtex field names.

    Args:
        identifier_field: Field name from identifier collection

    Returns:
        Corresponding bibtex field name
    """
    # Most fields map directly, but some need translation
    field_mapping = {
        "isbn13": "isbn",
        "arxiv": "eprint",  # arXiv IDs go to eprint field in biblatex
        "acmdl_doi": "url",  # ACM DL DOIs get converted to URLs
        # Add more mappings as needed
    }

    return field_mapping.get(identifier_field, identifier_field)


def _normalize_field_value(field_name: str, value: str, original_field: str = "") -> str:
    """Normalize field values for consistent formatting.

    Args:
        field_name: Name of the bibtex field
        value: Raw value from identifier collection
        original_field: Original field name from identifier collection (for special handling)

    Returns:
        Normalized value suitable for bibtex
    """
    if field_name == "isbn":
        # For ISBN, we could add hyphenation or format normalization
        # For now, just return as-is since both ISBN-10 and ISBN-13 are valid
        return value
    elif field_name == "doi":
        # Remove any "doi:" prefix if present (case insensitive)
        return re.sub(r"^doi:\s*", "", value, flags=re.IGNORECASE)
    elif field_name == "eprint":
        # For arXiv eprints, ensure proper format (remove arxiv: prefix if present)
        return re.sub(r"^(arxiv:|arXiv:)\s*", "", value)
    elif field_name == "url":
        # Handle special case: ACM DL DOI conversion to URL
        if original_field == "acmdl_doi":
            # Convert ACM DL DOI to proper ACM DL URL
            doi_part = re.sub(r"^doi:\s*", "", value)
            return f"https://dl.acm.org/doi/{doi_part}"

        # For regular URLs, ensure they're properly formatted
        if not value.startswith(("http://", "https://")):
            if value.startswith("//"):
                return f"https:{value}"
            else:
                return f"https://{value}"
        return value
    else:
        # Default: return as-is
        return value


def _field_needs_update(field_name: str, current_value: str | None, new_value: str) -> bool:
    """Check if a field needs to be updated.

    Args:
        field_name: Name of the bibtex field
        current_value: Current value in library.bib (None if field doesn't exist)
        new_value: New value from identifier collection

    Returns:
        True if field should be updated
    """
    # If field doesn't exist, always add it
    if current_value is None:
        return True

    # If values are identical, no update needed
    if current_value == new_value:
        return False

    # For ISBN, handle the case where library has multiple ISBNs
    if field_name == "isbn":
        # If current value contains multiple ISBNs, check if new value is already included
        current_isbns = {isbn.strip() for isbn in re.split(r"[,;]\s*", current_value)}
        if new_value in current_isbns:
            return False  # New ISBN already present, no update needed

        # If new value is ISBN-13 and we have corresponding ISBN-10, prefer ISBN-13
        new_isbn_digits = re.sub(r"[-\s]", "", new_value)
        if len(new_isbn_digits) == 13:  # New value is ISBN-13
            for existing_isbn in current_isbns:
                existing_digits = re.sub(r"[-\s]", "", existing_isbn)
                if len(existing_digits) == 10:  # Existing is ISBN-10
                    # We could check if they represent the same book, but for now
                    # just replace with the ISBN-13 as it's more standard
                    return True

    # Default: update if values differ
    return True

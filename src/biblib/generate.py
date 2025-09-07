"""Label generation module for biblatex entries."""

import hashlib
import json
import logging
import re
import unicodedata
from pathlib import Path

import bibtexparser

from .json_validation import validate_identifier_collection
from .types import IdentifierCollection

logger = logging.getLogger(__name__)


def extract_lastname(author_str: str, sortname_str: str = "") -> str:
    """Extract the first author's last name from author field.

    Args:
        author_str: Author field value from biblatex entry
        sortname_str: Optional sortname field for organizational authors

    Returns:
        Normalized lastname suitable for use in citekeys
    """
    if not author_str:
        return "unknown"

    # Handle multiple authors - take the first one
    first_author = author_str.split(" and ")[0].strip()

    # Check if the name is braced (organizational author)
    if first_author.startswith("{") and first_author.endswith("}"):
        # Remove braces
        first_author = first_author.strip("{}")

        # If there's a sortname field, use the first word of sortname
        if sortname_str:
            sortname_parts = sortname_str.split()
            lastname = sortname_parts[0] if sortname_parts else "unknown"
        else:
            # Otherwise, use the first word of author field
            author_parts = first_author.split()
            lastname = author_parts[0] if author_parts else "unknown"
    else:
        # Regular person name handling
        if "," in first_author:
            # Format: "Lastname, Firstname"
            lastname = first_author.split(",")[0].strip()
        else:
            # Format: "Firstname Lastname" - take the last word
            parts = first_author.split()
            lastname = parts[-1] if parts else "unknown"

    # Normalize Unicode characters (remove accents) and keep only letters
    # Convert to NFD (decomposed form) and remove combining characters
    lastname = unicodedata.normalize("NFD", lastname)
    lastname = "".join(c for c in lastname if unicodedata.category(c) != "Mn")

    # Clean up any remaining special characters and make lowercase
    lastname = re.sub(r"[^a-zA-Z]", "", lastname).lower()
    return lastname or "unknown"


def extract_year(year_str: str) -> str:
    """Extract year from date/year field.

    Args:
        year_str: Date or year field value from biblatex entry

    Returns:
        4-digit year string or "unknown" if not found
    """
    if not year_str:
        return "unknown"

    # Extract 4-digit year (19xx or 20xx)
    year_match = re.search(r"\b(19|20)\d{2}\b", year_str)
    if year_match:
        return year_match.group(0)

    return "unknown"


def create_hash(identifier: str) -> str:
    """Create SHA-256 hash of the identifier and return first 8 characters.

    Args:
        identifier: String to hash (typically DOI, ISBN, etc.)

    Returns:
        First 8 characters of SHA-256 hash as lowercase hex
    """
    hash_obj = hashlib.sha256(identifier.encode("utf-8"))
    return hash_obj.hexdigest()[:8]


def parse_bib_entries(bib_path: Path) -> dict[str, dict[str, str]]:
    """Parse bibtex file and extract entry information using bibtexparser v2.

    Args:
        bib_path: Path to the .bib file

    Returns:
        Dictionary mapping entry keys to entry data dictionaries

    Raises:
        FileNotFoundError: If bib file doesn't exist
        ValueError: If parsing fails
    """
    if not bib_path.exists():
        raise FileNotFoundError(f"Bibliography file not found: {bib_path}")

    logger.debug(f"Parsing .bib file for label generation: {bib_path}")

    try:
        lib = bibtexparser.parse_file(str(bib_path))

        if lib.failed_blocks:
            failed_keys = [str(block) for block in lib.failed_blocks]
            raise ValueError(f"Failed to parse {len(lib.failed_blocks)} blocks: {failed_keys}")

        entries: dict[str, dict[str, str]] = {}
        for entry in lib.entries:
            entry_key = entry.key
            entry_data: dict[str, str] = {
                "type": entry.entry_type,
                "key": entry_key,
                "author": "",
                "year": "",
                "sortname": "",
                "editor": "",
            }

            # Extract fields using bibtexparser v2 API
            fields_dict = entry.fields_dict

            # Extract author field
            if "author" in fields_dict:
                entry_data["author"] = fields_dict["author"].value

            # Extract editor field (fallback when no author)
            if "editor" in fields_dict:
                entry_data["editor"] = fields_dict["editor"].value

            # Extract sortname field
            if "sortname" in fields_dict:
                entry_data["sortname"] = fields_dict["sortname"].value

            # Extract year field (check date first, then year)
            if "date" in fields_dict:
                entry_data["year"] = fields_dict["date"].value
            elif "year" in fields_dict:
                entry_data["year"] = fields_dict["year"].value

            entries[entry_key] = entry_data

        logger.debug(f"Extracted {len(entries)} entries for label generation")
        return entries

    except Exception as e:
        raise ValueError(f"Failed to parse {bib_path}: {e}") from e


def load_identifier_collection(identifier_path: Path) -> IdentifierCollection:
    """Load identifier collection from JSON file.

    Args:
        identifier_path: Path to identifier_collection.json

    Returns:
        Dictionary with identifier data

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If JSON is invalid
    """
    if not identifier_path.exists():
        raise FileNotFoundError(f"Identifier collection file not found: {identifier_path}")

    logger.debug(f"Loading identifier collection: {identifier_path}")

    try:
        with open(identifier_path, encoding="utf-8") as f:
            data = json.load(f)

        # Use proper validation function to eliminate type warnings
        data_dict = validate_identifier_collection(data)
        logger.debug(f"Loaded {len(data_dict)} identifiers")
        return data_dict

    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in {identifier_path}: {e}") from e


def generate_labels(bib_path: Path, identifier_path: Path) -> dict[str, str]:
    """Generate labels for all biblatex entries.

    Args:
        bib_path: Path to library.bib
        identifier_path: Path to identifier_collection.json

    Returns:
        Dictionary mapping original entry keys to generated labels

    Raises:
        FileNotFoundError: If required files don't exist
        ValueError: If parsing fails
    """
    logger.info("Generating labels for biblatex entries")

    # Load data sources
    entries = parse_bib_entries(bib_path)
    identifier_collection = load_identifier_collection(identifier_path)

    labels: dict[str, str] = {}

    for entry_key, entry_data in entries.items():
        # Extract lastname and year - use author if available, otherwise editor
        author_field = entry_data.get("author", "") or entry_data.get("editor", "")
        lastname = extract_lastname(author_field, entry_data.get("sortname", ""))
        year = extract_year(entry_data.get("year", ""))

        # Get identifier for hashing
        if entry_key in identifier_collection:
            identifier_data = identifier_collection[entry_key]
            main_identifier = identifier_data.get("main_identifier")
            if main_identifier and main_identifier in identifier_data.get("identifiers", {}):
                identifier_value = identifier_data["identifiers"][main_identifier]
                hash_part = create_hash(identifier_value)
            else:
                # Fallback: use the entry key itself
                hash_part = create_hash(entry_key)
        else:
            # Entry not found in identifier collection, use entry key
            hash_part = create_hash(entry_key)

        # Generate label
        label = f"{lastname}-{year}-{hash_part}"
        labels[entry_key] = label

        logger.debug(f"{entry_key} -> {label}")

    logger.info(f"Generated {len(labels)} labels")
    return labels

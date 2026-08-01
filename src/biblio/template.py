"""Generate identifier collection templates from staging .bib files."""

import json
import logging
from pathlib import Path
from urllib.parse import urlsplit

import bibtexparser
from bibtexparser.model import Entry

from .config import BiblioConfig
from .exceptions import FileOperationError, InvalidDataError
from .normalize.isbn import (
    calculate_isbn13_check_digit,
    extract_isbn_digits,
    is_valid_isbn10,
    is_valid_isbn13,
)
from .types import IdentifierData

logger = logging.getLogger(__name__)

# Priority order for main identifier selection
MAIN_IDENTIFIER_PRIORITY = [
    "doi",
    "isbn13",
    "mrnumber",
    "arxiv",
    "zbmath",
    "zbl",
    "jfm",
    "oclc",
    "eprint",
    "url",
]

_ARXIV_DOI_PREFIX = "10.48550/arxiv."
_ARXIV_URL_HOSTS = {"arxiv.org", "www.arxiv.org"}


def _extract_arxiv_identifier_from_doi(doi: str) -> str | None:
    """Return the arXiv ID encoded by an arXiv-issued DataCite DOI."""
    normalized_doi = doi.strip()
    if not normalized_doi.casefold().startswith(_ARXIV_DOI_PREFIX):
        return None

    identifier = normalized_doi[len(_ARXIV_DOI_PREFIX) :]
    return identifier or None


def _extract_arxiv_identifier_from_url(url: str) -> str | None:
    """Return the arXiv ID encoded by a canonical abstract or PDF URL."""
    try:
        parsed_url = urlsplit(url.strip())
        hostname = parsed_url.hostname
    except ValueError:
        return None

    if (
        parsed_url.scheme.casefold() not in {"http", "https"}
        or hostname is None
        or hostname.casefold() not in _ARXIV_URL_HOSTS
    ):
        return None

    route, separator, identifier = parsed_url.path.lstrip("/").partition("/")
    if not separator or route.casefold() not in {"abs", "pdf"}:
        return None

    identifier = identifier.rstrip("/")
    if route.casefold() == "pdf" and identifier.casefold().endswith(".pdf"):
        identifier = identifier[:-4]

    return identifier or None


def _identifiers_match(first: str | None, second: str | None) -> bool:
    """Return whether two non-empty identifiers match case-insensitively."""
    return first is not None and second is not None and first.casefold() == second.casefold()


def _remove_redundant_arxiv_identifiers(identifiers: dict[str, str]) -> None:
    """Keep an arXiv eprint instead of its derived DOI and URL forms."""
    arxiv_identifier = identifiers.get("arxiv")
    doi_arxiv_identifier = _extract_arxiv_identifier_from_doi(identifiers.get("doi", ""))
    url_arxiv_identifier = _extract_arxiv_identifier_from_url(identifiers.get("url", ""))

    if _identifiers_match(url_arxiv_identifier, arxiv_identifier) or _identifiers_match(
        url_arxiv_identifier, doi_arxiv_identifier
    ):
        identifiers.pop("url", None)

    if _identifiers_match(arxiv_identifier, doi_arxiv_identifier):
        identifiers.pop("doi", None)


def _extract_identifiers_from_entry(entry: Entry) -> dict[str, str]:
    """Extract identifier fields from a bibtex entry.

    Args:
        entry: Bibtex entry to process

    Returns:
        Dictionary mapping identifier names to values
    """
    identifiers: dict[str, str] = {}

    # Check if this is an arXiv entry based on archiveprefix or eprinttype
    is_arxiv = False

    # Create a case-insensitive lookup for fields to handle variations like archivePrefix
    fields_lower = {k.lower(): v for k, v in entry.fields_dict.items()}

    for type_field in ["archiveprefix", "eprinttype"]:
        if type_field in fields_lower:
            value = str(fields_lower[type_field].value).strip().lower()
            if value == "arxiv":
                is_arxiv = True
                break

    # Common identifier field mappings
    identifier_fields = {
        "doi": "doi",
        "isbn": "isbn13",  # Map bib 'isbn' to 'isbn13' in output
        "url": "url",
        "mrnumber": "mrnumber",
        "eprint": "arxiv" if is_arxiv else "eprint",  # Map eprint to arxiv if it's an arXiv entry
        "zbl": "zbl",
        "zbmath": "zbmath",
        "jfm": "jfm",  # Jahrbuch für die Fortschritte der Mathematik
        "oclc": "oclc",
        "mathscinet": "mrnumber",  # Alternative field name
        "arxiv": "arxiv",  # Explicit arxiv field maps to arxiv
    }

    for field_name, field_obj in entry.fields_dict.items():
        field_name_lower = field_name.lower()
        if field_name_lower in identifier_fields:
            identifier_key = identifier_fields[field_name_lower]
            identifier_value = str(field_obj.value).strip()

            if identifier_value:
                # Clean up common prefixes/formats
                if identifier_key == "doi" and identifier_value.startswith("https://doi.org/"):
                    identifier_value = identifier_value.replace("https://doi.org/", "")
                elif identifier_key == "eprint" and identifier_value.startswith("arXiv:"):
                    identifier_value = identifier_value.replace("arXiv:", "")
                elif identifier_key == "arxiv" and identifier_value.startswith("arXiv:"):
                    identifier_value = identifier_value.replace("arXiv:", "")
                elif identifier_key == "isbn13":
                    digits = extract_isbn_digits(identifier_value)
                    if len(digits) == 13 and is_valid_isbn13(digits):
                        identifier_value = digits
                    elif len(digits) == 10 and is_valid_isbn10(digits):
                        isbn13_base = "978" + digits[:9]
                        check_digit = calculate_isbn13_check_digit(isbn13_base)
                        identifier_value = isbn13_base + check_digit
                    else:
                        identifier_value = identifier_value.replace("-", "")

                identifiers[identifier_key] = identifier_value

    # Exclude trivial URL that is just doi.org/<doi>
    if "doi" in identifiers and "url" in identifiers:
        doi_value = identifiers["doi"]
        url_value = identifiers["url"]
        if url_value in (
            f"https://doi.org/{doi_value}",
            f"http://doi.org/{doi_value}",
            f"https://dx.doi.org/{doi_value}",
            f"http://dx.doi.org/{doi_value}",
        ):
            del identifiers["url"]

    _remove_redundant_arxiv_identifiers(identifiers)

    return identifiers


def _select_main_identifier(identifiers: dict[str, str]) -> str | None:
    """Select main identifier based on priority order.

    Args:
        identifiers: Dictionary of available identifiers

    Returns:
        The main identifier field name, or None if no suitable identifier found
    """
    for priority_field in MAIN_IDENTIFIER_PRIORITY:
        if priority_field in identifiers:
            return priority_field

    return None


def _create_identifier_data(entry: Entry) -> IdentifierData:
    """Create identifier data structure for a single entry.

    Args:
        entry: Bibtex entry to process

    Returns:
        IdentifierData structure
    """
    identifiers = _extract_identifiers_from_entry(entry)
    main_identifier = _select_main_identifier(identifiers)

    return {
        "main_identifier": main_identifier or "",  # Provide empty string if None
        "identifiers": identifiers,
    }


def generate_identifier_template(bib_file: Path) -> dict[str, IdentifierData]:
    """Generate identifier collection template from a .bib file.

    Args:
        bib_file: Path to .bib file to process

    Returns:
        Dictionary mapping citekeys to identifier data

    Raises:
        FileOperationError: If file cannot be read
        InvalidDataError: If .bib file cannot be parsed
    """
    logger.info(f"Generating identifier template for {bib_file.name}")

    try:
        # Parse the .bib file
        library = bibtexparser.parse_file(str(bib_file))

        if library.failed_blocks:
            failed_keys = [str(block) for block in library.failed_blocks]
            raise InvalidDataError(
                f"Failed to parse {len(library.failed_blocks)} blocks: {failed_keys}"
            )

        # Generate identifier data for each entry
        identifier_collection: dict[str, IdentifierData] = {}

        for entry in library.entries:
            if not entry.key:
                logger.warning(f"Entry without citekey found in {bib_file.name}")
                continue

            identifier_data = _create_identifier_data(entry)
            identifier_collection[entry.key] = identifier_data

            logger.debug(f"Generated identifier data for {entry.key}: {identifier_data}")

        logger.info(f"Generated identifier template with {len(identifier_collection)} entries")
        return identifier_collection

    except (OSError, PermissionError) as e:
        raise FileOperationError(f"Failed to read {bib_file}: {e}") from e
    except UnicodeDecodeError as e:
        raise FileOperationError(f"Failed to decode {bib_file}: {e}") from e
    except Exception as e:
        # Catch bibtexparser errors
        raise InvalidDataError(f"Failed to parse {bib_file}: {e}") from e


def generate_staging_templates(
    config: BiblioConfig, overwrite: bool = False
) -> tuple[int, list[str]]:
    """Generate identifier templates for all .bib files in staging without .json companions.

    Args:
        config: Resolved workspace configuration
        overwrite: Whether to overwrite existing .json files

    Returns:
        Tuple of (files_processed, list_of_generated_files)
    """

    if not config.staging_dir.exists():
        logger.warning(f"Staging directory does not exist: {config.staging_dir}")
        return 0, []

    generated_files: list[str] = []
    files_processed = 0

    # Find all .bib files in staging
    for bib_file in config.staging_dir.glob("*.bib"):
        # Check if corresponding .json file exists
        json_file = bib_file.with_suffix(".json")

        if json_file.exists() and not overwrite:
            logger.debug(f"Skipping {bib_file.name}, .json file already exists")
            continue

        try:
            # Generate identifier template
            identifier_template = generate_identifier_template(bib_file)

            # Write to .json file with UTF-8 encoding
            with open(json_file, "w", encoding="utf-8") as f:
                json.dump(identifier_template, f, indent=2, ensure_ascii=False)

            generated_files.append(json_file.name)
            files_processed += 1

            logger.info(f"Generated {json_file.name} with {len(identifier_template)} entries")

        except (FileOperationError, InvalidDataError) as e:
            logger.error(f"Failed to process {bib_file.name}: {e}")
            continue

    if files_processed > 0:
        logger.info(f"Generated {files_processed} identifier templates")
    else:
        logger.info("No new templates to generate")

    return files_processed, generated_files

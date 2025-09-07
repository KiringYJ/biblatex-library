"""Generate identifier collection templates from staging .bib files."""

import json
import logging
from pathlib import Path

import bibtexparser
from bibtexparser.model import Entry

from .config import WorkspaceConfig
from .exceptions import FileOperationError, InvalidDataError
from .types import IdentifierData

logger = logging.getLogger(__name__)

# Priority order for main identifier selection
MAIN_IDENTIFIER_PRIORITY = ["doi", "isbn", "mrnumber", "url"]


def _extract_identifiers_from_entry(entry: Entry) -> dict[str, str]:
    """Extract identifier fields from a bibtex entry.

    Args:
        entry: Bibtex entry to process

    Returns:
        Dictionary mapping identifier names to values
    """
    identifiers: dict[str, str] = {}

    # Common identifier field mappings
    identifier_fields = {
        "doi": "doi",
        "isbn": "isbn",
        "url": "url",
        "mrnumber": "mrnumber",
        "eprint": "eprint",  # arXiv
        "zbl": "zbl",
        "mathscinet": "mrnumber",  # Alternative field name
        "arxiv": "eprint",  # Alternative field name
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

                identifiers[identifier_key] = identifier_value

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

    # Fallback to first available identifier field name
    if identifiers:
        return next(iter(identifiers.keys()))

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


def generate_staging_templates(workspace: Path, overwrite: bool = False) -> tuple[int, list[str]]:
    """Generate identifier templates for all .bib files in staging without .json companions.

    Args:
        workspace: Path to workspace root
        overwrite: Whether to overwrite existing .json files

    Returns:
        Tuple of (files_processed, list_of_generated_files)
    """
    config = WorkspaceConfig.from_workspace(workspace)

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

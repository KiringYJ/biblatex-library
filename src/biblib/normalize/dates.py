"""Normalization helpers for biblatex date fields."""

from __future__ import annotations

import logging
from pathlib import Path

import bibtexparser
from bibtexparser.library import Library
from bibtexparser.model import Entry, Field

logger = logging.getLogger(__name__)


def rename_year_to_date_fields(
    library_path: Path, *, dry_run: bool = False
) -> tuple[int, list[str]]:
    """Normalize date fields in a biblatex library.

    For each entry in ``library_path`` that has a ``year`` field but no ``date`` field,
    rename the field to ``date``.

    Args:
        library_path: Path to the ``library.bib`` file to update.
        dry_run: If ``True`` report the number of changes without writing to disk.

    Returns:
        A tuple ``(updated_count, updated_keys)`` describing the changes that were made
        (or would be made for a dry run).

    Raises:
        FileNotFoundError: If ``library_path`` does not exist.
        ValueError: If the bib file cannot be parsed.
    """
    if not library_path.exists():
        raise FileNotFoundError(f"Bibliography file not found: {library_path}")

    logger.debug("Loading library for date normalization: %s", library_path)

    try:
        library: Library = bibtexparser.parse_file(str(library_path))
    except Exception as exc:  # pragma: no cover - library raises many custom exceptions
        raise ValueError(f"Failed to parse {library_path}: {exc}") from exc

    updated_keys: list[str] = []

    for entry in library.entries:
        if _rename_year_field(entry):
            updated_keys.append(entry.key)
            logger.info("Converted year -> date for entry %s", entry.key)

    if not updated_keys:
        logger.info("No year fields required conversion in %s", library_path)
        return 0, []

    if dry_run:
        logger.info(
            "Dry run: %d entries would have their year field renamed to date", len(updated_keys)
        )
        return len(updated_keys), updated_keys

    logger.debug("Writing normalized library back to disk: %s", library_path)

    bibtex_string = bibtexparser.write_string(library)
    with open(library_path, "w", encoding="utf-8") as bib_file:
        bib_file.write(str(bibtex_string))

    logger.info("Updated %d entries (year -> date) in %s", len(updated_keys), library_path.name)
    return len(updated_keys), updated_keys


def _rename_year_field(entry: Entry) -> bool:
    """Rename the ``year`` field to ``date`` for a single entry.

    Returns ``True`` if the entry was modified.
    """
    fields = entry.fields_dict

    if "date" in fields or "year" not in fields:
        return False

    year_field = fields["year"]

    for index, field in enumerate(entry.fields):
        if field is year_field:
            entry.fields[index] = Field("date", year_field.value)
            break
    else:  # pragma: no cover - defensive, we already found the field via dict lookup
        entry.fields.append(Field("date", year_field.value))

    return True

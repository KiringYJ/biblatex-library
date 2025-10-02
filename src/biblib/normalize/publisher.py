"""Normalization helpers for publisher/location fields."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import bibtexparser
from bibtexparser.library import Library
from bibtexparser.model import Entry, Field

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PublisherLocationReport:
    """Summary of publisher/location normalization."""

    flagged: list[str]
    fixed: list[str]


def normalize_publisher_location(
    library_path: Path, *, dry_run: bool = False
) -> PublisherLocationReport:
    """Ensure entries have a location when a publisher is present.

    Any entry with ``publisher`` but no ``location`` is flagged. If the publisher
    field contains exactly one comma, split it into publisher/location values.

    Args:
        library_path: Path to the ``library.bib`` file to update.
        dry_run: If ``True`` report planned changes without modifying files.

    Returns:
        A :class:`PublisherLocationReport` detailing flagged and fixed citekeys.

    Raises:
        FileNotFoundError: If ``library_path`` does not exist.
        ValueError: If the bib file cannot be parsed.
    """
    if not library_path.exists():
        raise FileNotFoundError(f"Bibliography file not found: {library_path}")

    logger.debug("Loading library for publisher/location normalization: %s", library_path)

    try:
        library: Library = bibtexparser.parse_file(str(library_path))
    except Exception as exc:  # pragma: no cover - parser raises custom errors
        raise ValueError(f"Failed to parse {library_path}: {exc}") from exc

    flagged: list[str] = []
    fixed: list[str] = []

    for entry in library.entries:
        if entry.entry_type.lower() == "article":
            logger.debug(
                "Skipping publisher/location normalization for article entry: %s",
                entry.key,
            )
            continue

        if not _needs_location(entry):
            continue

        flagged.append(entry.key)

        if _split_publisher(entry, dry_run=dry_run):
            fixed.append(entry.key)

    if fixed and not dry_run:
        logger.debug("Writing publisher/location updates back to disk: %s", library_path)
        bibtex_string = bibtexparser.write_string(library)
        with open(library_path, "w", encoding="utf-8") as bib_file:
            bib_file.write(str(bibtex_string))

    return PublisherLocationReport(flagged=flagged, fixed=fixed)


def _needs_location(entry: Entry) -> bool:
    fields = entry.fields_dict
    return "publisher" in fields and "location" not in fields


def _split_publisher(entry: Entry, *, dry_run: bool) -> bool:
    fields = entry.fields_dict
    publisher_field = fields["publisher"]
    publisher_value = str(publisher_field.value)
    if publisher_value.count(",") != 1:
        logger.info(
            "Publisher without clear location (manual review needed): %s -> %s",
            entry.key,
            publisher_value,
        )
        return False
    parts = [part.strip() for part in publisher_value.split(",", 1)]

    if len(parts) != 2 or not all(parts):
        logger.info(
            "Publisher without location (manual review needed): %s -> %s",
            entry.key,
            publisher_value,
        )
        return False

    logger.info(
        "Splitting publisher/location for %s: '%s' -> publisher='%s', location='%s'",
        entry.key,
        publisher_value,
        parts[0],
        parts[1],
    )

    if not dry_run:
        publisher_field.value = parts[0]
        entry.fields.append(Field("location", parts[1]))

    return True

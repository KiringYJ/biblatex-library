"""Normalization helpers for eprint-related fields."""

from __future__ import annotations

import logging
from collections.abc import MutableMapping
from dataclasses import dataclass
from pathlib import Path

import bibtexparser
from bibtexparser.library import Library
from bibtexparser.model import Entry, Field

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class EprintNormalizationReport:
    """Summary of eprint field normalization."""

    renamed_type: list[str]
    renamed_class: list[str]
    normalized_type: list[str]
    changed_entry_type: list[str]  # misc -> online for arXiv entries


def normalize_eprint_fields(
    library_path: Path, *, dry_run: bool = False
) -> EprintNormalizationReport:
    """Normalize legacy arXiv field names and values.

    - Renames ``archiveprefix`` → ``eprinttype``
    - Renames ``primaryclass`` → ``eprintclass``
    - Ensures ``eprinttype`` value uses lowercase ``arxiv``
    - Changes entry type from ``misc`` to ``online`` for arXiv entries

    Args:
        library_path: Path to ``library.bib``
        dry_run: When ``True``, report changes without writing to disk

    Returns:
        :class:`EprintNormalizationReport` describing applied changes

    Raises:
        FileNotFoundError: If ``library_path`` does not exist
        ValueError: If the bib file cannot be parsed
    """
    if not library_path.exists():
        raise FileNotFoundError(f"Bibliography file not found: {library_path}")

    logger.debug("Loading library for eprint normalization: %s", library_path)

    try:
        library: Library = bibtexparser.parse_file(str(library_path))
    except Exception as exc:  # pragma: no cover - parser raises custom errors
        raise ValueError(f"Failed to parse {library_path}: {exc}") from exc

    renamed_type: list[str] = []
    renamed_class: list[str] = []
    normalized_type: list[str] = []
    changed_entry_type: list[str] = []

    for entry in library.entries:
        fields: MutableMapping[str, Field] = entry.fields_dict
        archive_field = fields.get("archiveprefix")
        archive_value = str(archive_field.value) if archive_field is not None else None

        if _rename_field(entry, fields, "archiveprefix", "eprinttype", dry_run):
            renamed_type.append(entry.key)
        if _rename_field(entry, fields, "primaryclass", "eprintclass", dry_run):
            renamed_class.append(entry.key)

        if _normalize_eprinttype(entry, entry.fields_dict, archive_value, dry_run):
            normalized_type.append(entry.key)

        if _change_arxiv_entry_type(entry, dry_run):
            changed_entry_type.append(entry.key)

    if not dry_run and any([renamed_type, renamed_class, normalized_type, changed_entry_type]):
        logger.debug("Writing eprint normalization changes back to disk: %s", library_path)
        bibtex_string = bibtexparser.write_string(library)
        with open(library_path, "w", encoding="utf-8") as bib_file:
            bib_file.write(str(bibtex_string))

    return EprintNormalizationReport(
        renamed_type=renamed_type,
        renamed_class=renamed_class,
        normalized_type=normalized_type,
        changed_entry_type=changed_entry_type,
    )


def _rename_field(
    entry: Entry,
    fields: MutableMapping[str, Field],
    old_name: str,
    new_name: str,
    dry_run: bool,
) -> bool:
    if old_name not in fields:
        return False

    old_field = fields[old_name]
    new_value = str(old_field.value)

    logger.info(
        "Renaming %s -> %s for entry %s (value='%s')",
        old_name,
        new_name,
        entry.key,
        new_value,
    )

    if dry_run:
        return True

    _remove_field(entry, old_name)
    _set_field(entry, new_name, new_value)
    return True


def _normalize_eprinttype(
    entry: Entry,
    fields: MutableMapping[str, Field],
    archive_value: str | None,
    dry_run: bool,
) -> bool:
    field = fields.get("eprinttype")

    current_value: str | None
    if field is not None:
        current_value = str(field.value)
    else:
        current_value = archive_value

    if current_value is None:
        return False

    if current_value.lower() != "arxiv":
        return False
    if current_value == "arxiv":
        return False

    logger.info(
        "Normalizing eprinttype for entry %s: '%s' -> 'arxiv'",
        entry.key,
        current_value,
    )

    if dry_run:
        return True

    if field is not None:
        field.value = "arxiv"
    else:
        _set_field(entry, "eprinttype", "arxiv")

    return True


def _change_arxiv_entry_type(entry: Entry, dry_run: bool) -> bool:
    """Change entry type from misc to online for arXiv entries.

    Args:
        entry: The bibtex entry to check
        dry_run: If True, don't actually modify the entry

    Returns:
        True if the entry type was changed, False otherwise
    """
    # Only change misc entries
    if entry.entry_type.lower() != "misc":
        return False

    # Check if this is an arXiv entry (has eprinttype=arxiv or archiveprefix=arxiv)
    fields = entry.fields_dict
    eprinttype = fields.get("eprinttype")
    archiveprefix = fields.get("archiveprefix")

    is_arxiv = False
    if eprinttype is not None and str(eprinttype.value).lower() == "arxiv":
        is_arxiv = True
    elif archiveprefix is not None and str(archiveprefix.value).lower() == "arxiv":
        is_arxiv = True

    if not is_arxiv:
        return False

    logger.info(
        "Changing entry type for %s: 'misc' -> 'online'",
        entry.key,
    )

    if dry_run:
        return True

    entry.entry_type = "online"
    return True


def _remove_field(entry: Entry, field_name: str) -> None:
    field_obj = entry.fields_dict.get(field_name)
    if field_obj is None:
        return
    for index, field in enumerate(entry.fields):
        if field is field_obj:
            entry.fields.pop(index)
            break


def _set_field(entry: Entry, field_name: str, value: str) -> None:
    existing = entry.fields_dict.get(field_name)
    if existing is not None:
        existing.value = value
        return

    entry.fields.append(Field(field_name, value))

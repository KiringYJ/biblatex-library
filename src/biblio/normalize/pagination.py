"""Whole-book page-extent normalization."""

import re
from dataclasses import dataclass, field

from bibtexparser.model import Entry, Field

from biblio.bibliography import Bibliography
from biblio.results import ChangeSet, FieldDelta

_UNAMBIGUOUS_EXTENT = re.compile(r"^(?:[ivxlcdm]+\s*\+\s*)?[1-9][0-9]*$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class BookPaginationReport:
    """Book pagination changes plus conflicting extents."""

    conflicts: tuple[str, ...] = ()
    ambiguous: tuple[str, ...] = ()
    changes: ChangeSet = field(default_factory=ChangeSet)


def normalize_book_pagination(bibliography: Bibliography) -> BookPaginationReport:
    """Treat ``pages`` on a whole ``book`` record as ``pagetotal``."""
    changed_keys: list[str] = []
    conflicts: list[str] = []
    ambiguous: list[str] = []
    deltas: list[FieldDelta] = []

    for entry in bibliography:
        if entry.entry_type.casefold() != "book":
            continue
        pages_field = entry.fields_dict.get("pages")
        if pages_field is None:
            continue
        pagetotal_field = entry.fields_dict.get("pagetotal")
        if pagetotal_field is not None and str(pagetotal_field.value) != str(pages_field.value):
            conflicts.append(entry.key)
            continue
        if not is_unambiguous_book_extent(str(pages_field.value)):
            ambiguous.append(entry.key)
            continue
        outcome = _normalize_entry(entry)
        assert outcome not in (None, ())
        changed_keys.append(entry.key)
        deltas.extend(outcome)

    return BookPaginationReport(
        tuple(conflicts),
        tuple(ambiguous),
        ChangeSet(tuple(changed_keys), tuple(deltas)),
    )


def is_unambiguous_book_extent(value: str) -> bool:
    """Return whether *value* is a single total or roman-plus-arabic extent."""
    return _UNAMBIGUOUS_EXTENT.fullmatch(value.strip()) is not None


def _normalize_entry(entry: Entry) -> tuple[FieldDelta, ...] | None:
    fields = entry.fields_dict
    pages_field = fields.get("pages")
    if pages_field is None:
        return None

    pages_value = str(pages_field.value)
    pagetotal_field = fields.get("pagetotal")
    if pagetotal_field is not None and str(pagetotal_field.value) != pages_value:
        return ()

    if pagetotal_field is None:
        replacement = Field("pagetotal", pages_field.value)
        position = entry.fields.index(pages_field)
        entry.fields[position] = replacement
        return (
            FieldDelta(entry.key, "pages", pages_value, None),
            FieldDelta(entry.key, "pagetotal", None, pages_value),
        )

    entry.fields.remove(pages_field)
    return (FieldDelta(entry.key, "pages", pages_value, None),)

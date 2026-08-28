"""Exact page-extent migration under the explicitly marked MR book convention."""

import re
from dataclasses import dataclass, field

from bibtexparser.model import Entry, Field

from biblio.bibliography import Bibliography
from biblio.results import ChangeSet, FieldDelta

from .mr import MR_FIELDS, has_mr_metadata

_ROMAN = r"M{0,3}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})"
_EXTENT = re.compile(rf"(?:(?=[MDCLXVI]){_ROMAN}\s*\+\s*)?[1-9][0-9]*", re.IGNORECASE | re.ASCII)
_PARTICIPATING_FIELDS = MR_FIELDS | {
    "pages",
    "pagetotal",
    "chapter",
    "pagination",
    "bookpagination",
}


@dataclass(frozen=True, slots=True)
class BookPaginationReport:
    """MR book extent changes, conflicting totals, and inputs left for review."""

    conflicts: tuple[str, ...] = ()
    ambiguous: tuple[str, ...] = ()
    changes: ChangeSet = field(default_factory=ChangeSet)


def is_supported_book_extent(value: str) -> bool:
    """Accept a positive count or canonical Roman preliminaries plus that count."""
    return _EXTENT.fullmatch(value.strip()) is not None


def is_mr_book_extent(entry: Entry) -> bool:
    """Check the source convention and scope, before comparing a target value."""
    fields = {item.key.casefold(): str(item.value) for item in entry.fields}
    return (
        entry.entry_type.casefold() == "book"
        and len(fields) == len(entry.fields)
        and has_mr_metadata(entry)
        and "pages" in fields
        and "chapter" not in fields
        and all(fields.get(unit, "page") == "page" for unit in ("pagination", "bookpagination"))
        and is_supported_book_extent(fields["pages"])
    )


def normalize_book_pagination(bibliography: Bibliography) -> BookPaginationReport:
    """Rename marked whole-book extents without changing their exact strings."""
    entries = [(entry, _participating_fields(entry)) for entry in bibliography]
    changed: list[str] = []
    conflicts: list[str] = []
    ambiguous: list[str] = []
    deltas: list[FieldDelta] = []
    for entry, fields in entries:
        if entry.entry_type.casefold() != "book" or "pages" not in fields:
            continue
        if not is_mr_book_extent(entry):
            ambiguous.append(entry.key)
            continue
        source = fields["pages"]
        value = str(source.value)
        target = fields.get("pagetotal")
        if target is not None and str(target.value) != value:
            conflicts.append(entry.key)
            continue
        deltas.append(FieldDelta(entry.key, "pages", value, None))
        if target is None:
            entry.fields[entry.fields.index(source)] = Field("pagetotal", source.value)
            deltas.append(FieldDelta(entry.key, "pagetotal", None, value))
        else:
            entry.fields.remove(source)
        changed.append(entry.key)
    return BookPaginationReport(
        tuple(conflicts), tuple(ambiguous), ChangeSet(tuple(changed), tuple(deltas))
    )


def _participating_fields(entry: Entry) -> dict[str, Field]:
    fields: dict[str, Field] = {}
    for entry_field in entry.fields:
        name = entry_field.key.casefold()
        if name not in _PARTICIPATING_FIELDS:
            continue
        if name in fields:
            raise ValueError(f"entry '{entry.key}' has duplicate '{name}' fields")
        fields[name] = entry_field
    return fields

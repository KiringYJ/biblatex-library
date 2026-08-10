"""Pure normalization helpers for eprint-related fields."""

from collections.abc import MutableMapping
from dataclasses import dataclass, field

from bibtexparser.model import Entry, Field

from biblio.bibliography import Bibliography
from biblio.results import ChangeSet, FieldDelta


@dataclass(frozen=True, slots=True)
class EprintNormalizationReport:
    """Summary of eprint field normalization."""

    renamed_type: tuple[str, ...] = ()
    renamed_class: tuple[str, ...] = ()
    normalized_type: tuple[str, ...] = ()
    changed_entry_type: tuple[str, ...] = ()
    changes: ChangeSet = field(default_factory=ChangeSet)


def normalize_eprint_fields(bibliography: Bibliography) -> EprintNormalizationReport:
    """Normalize legacy arXiv field names, values, and ``misc`` entry types."""
    renamed_type: list[str] = []
    renamed_class: list[str] = []
    normalized_type: list[str] = []
    changed_entry_type: list[str] = []
    deltas: list[FieldDelta] = []

    for entry in bibliography:
        fields: MutableMapping[str, Field] = entry.fields_dict
        archive_field = fields.get("archiveprefix")
        archive_value = str(archive_field.value) if archive_field is not None else None

        delta = _rename_field(entry, fields, "archiveprefix", "eprinttype")
        if delta:
            renamed_type.append(entry.key)
            deltas.extend(delta)
        delta = _rename_field(entry, entry.fields_dict, "primaryclass", "eprintclass")
        if delta:
            renamed_class.append(entry.key)
            deltas.extend(delta)

        delta = _normalize_eprinttype(entry, archive_value)
        if delta is not None:
            normalized_type.append(entry.key)
            deltas.append(delta)

        delta = _change_arxiv_entry_type(entry)
        if delta is not None:
            changed_entry_type.append(entry.key)
            deltas.append(delta)

    changed = set(renamed_type + renamed_class + normalized_type + changed_entry_type)
    changed_keys = tuple(entry.key for entry in bibliography if entry.key in changed)
    changes = ChangeSet(changed_keys, tuple(deltas))
    return EprintNormalizationReport(
        tuple(renamed_type),
        tuple(renamed_class),
        tuple(normalized_type),
        tuple(changed_entry_type),
        changes,
    )


def _rename_field(
    entry: Entry,
    fields: MutableMapping[str, Field],
    old_name: str,
    new_name: str,
) -> tuple[FieldDelta, ...]:
    old_field = fields.get(old_name)
    if old_field is None:
        return ()
    value = str(old_field.value)
    existing = fields.get(new_name)
    existing_value = str(existing.value) if existing is not None else None
    _remove_field(entry, old_name)
    _set_field(entry, new_name, value)
    return (
        FieldDelta(entry.key, old_name, value, None),
        FieldDelta(entry.key, new_name, existing_value, value),
    )


def _normalize_eprinttype(entry: Entry, archive_value: str | None) -> FieldDelta | None:
    field = entry.fields_dict.get("eprinttype")
    current = str(field.value) if field is not None else archive_value
    if current is None or current.casefold() != "arxiv" or current == "arxiv":
        return None
    if field is None:
        _set_field(entry, "eprinttype", "arxiv")
    else:
        field.value = "arxiv"
    return FieldDelta(entry.key, "eprinttype", current, "arxiv")


def _change_arxiv_entry_type(entry: Entry) -> FieldDelta | None:
    if entry.entry_type.casefold() != "misc":
        return None
    fields = entry.fields_dict
    eprinttype = fields.get("eprinttype")
    if eprinttype is None:
        eprinttype = fields.get("archiveprefix")
    if eprinttype is None or str(eprinttype.value).casefold() != "arxiv":
        return None
    before = entry.entry_type
    entry.entry_type = "online"
    return FieldDelta(entry.key, "entry_type", before, "online")


def _remove_field(entry: Entry, field_name: str) -> None:
    field_obj = entry.fields_dict.get(field_name)
    if field_obj is not None:
        entry.fields.remove(field_obj)


def _set_field(entry: Entry, field_name: str, value: str) -> None:
    existing = entry.fields_dict.get(field_name)
    if existing is not None:
        existing.value = value
    else:
        entry.fields.append(Field(field_name, value))

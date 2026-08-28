"""Eprint aliases and the explicit arXiv miscellaneous-entry import convention."""

from dataclasses import dataclass, field

from bibtexparser.model import Entry, Field

from biblio.bibliography import Bibliography
from biblio.results import ChangeSet, FieldDelta

_ALIASES = (("archiveprefix", "eprinttype"), ("primaryclass", "eprintclass"))
_PARTICIPATING_FIELDS = {name for pair in _ALIASES for name in pair} | {"eprint"}


@dataclass(frozen=True, slots=True)
class EprintNormalizationReport:
    """Summary of alias migration, arXiv type conversion, and preserved conflicts."""

    renamed_type: tuple[str, ...] = ()
    renamed_class: tuple[str, ...] = ()
    normalized_type: tuple[str, ...] = ()
    conflicts: tuple[tuple[str, str, str], ...] = ()
    changes: ChangeSet = field(default_factory=ChangeSet)
    changed_entry_type: tuple[str, ...] = ()


def normalize_eprint_fields(bibliography: Bibliography) -> EprintNormalizationReport:
    """Migrate aliases and convert explicit arXiv ``misc`` records to ``online``.

    Require a nonempty eprint and preserve every other entry type. Alias
    conflicts preserve the complete eprint namespace and the original type.
    """
    renamed_type: list[str] = []
    renamed_class: list[str] = []
    normalized_type: list[str] = []
    conflicts: list[tuple[str, str, str]] = []
    changed_entry_type: list[str] = []
    deltas: list[FieldDelta] = []
    entries = [(entry, _eprint_fields(entry)) for entry in bibliography]

    for entry, fields in entries:
        entry_conflicts = [
            (entry.key, source, target)
            for source, target in _ALIASES
            if source in fields
            and target in fields
            and not _alias_values_equal(
                source, str(fields[source].value), str(fields[target].value)
            )
        ]
        if entry_conflicts:
            conflicts.extend(entry_conflicts)
            continue

        for (source, target), renamed in zip(_ALIASES, (renamed_type, renamed_class), strict=True):
            old_field = fields.get(source)
            if old_field is None:
                continue
            deltas.extend(_rename_field(entry, old_field, target, fields.get(target)))
            renamed.append(entry.key)

        eprinttype = next(
            (item for item in entry.fields if item.key.casefold() == "eprinttype"), None
        )
        if eprinttype is not None:
            value = str(eprinttype.value)
            if value.casefold() == "arxiv" and value != "arxiv":
                eprinttype.value = "arxiv"
                normalized_type.append(entry.key)
                deltas.append(FieldDelta(entry.key, "eprinttype", value, "arxiv"))

        eprint = fields.get("eprint")
        if (
            entry.entry_type.casefold() == "misc"
            and eprinttype is not None
            and str(eprinttype.value).strip().casefold() == "arxiv"
            and eprint is not None
            and str(eprint.value).strip()
        ):
            before = entry.entry_type
            entry.entry_type = "online"
            changed_entry_type.append(entry.key)
            deltas.append(FieldDelta(entry.key, "entry_type", before, "online"))

    changed = set(renamed_type + renamed_class + normalized_type + changed_entry_type)
    changes = ChangeSet(
        tuple(entry.key for entry in bibliography if entry.key in changed), tuple(deltas)
    )
    return EprintNormalizationReport(
        renamed_type=tuple(renamed_type),
        renamed_class=tuple(renamed_class),
        normalized_type=tuple(normalized_type),
        conflicts=tuple(conflicts),
        changes=changes,
        changed_entry_type=tuple(changed_entry_type),
    )


def _eprint_fields(entry: Entry) -> dict[str, Field]:
    fields: dict[str, Field] = {}
    for entry_field in entry.fields:
        name = entry_field.key.casefold()
        if name not in _PARTICIPATING_FIELDS:
            continue
        if name in fields:
            raise ValueError(f"entry '{entry.key}' has duplicate '{name}' fields")
        fields[name] = entry_field
    return fields


def _alias_values_equal(source: str, old: str, new: str) -> bool:
    return old == new or (source == "archiveprefix" and old.casefold() == new.casefold() == "arxiv")


def _rename_field(
    entry: Entry, old_field: Field, target: str, existing: Field | None
) -> tuple[FieldDelta, ...]:
    value = str(old_field.value)
    removal = FieldDelta(entry.key, old_field.key.casefold(), value, None)
    if existing is not None:
        entry.fields.remove(old_field)
        return (removal,)
    entry.fields[entry.fields.index(old_field)] = Field(target, old_field.value)
    return (removal, FieldDelta(entry.key, target, None, value))

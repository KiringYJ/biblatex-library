"""Pure representation normalization for documented eprint field aliases."""

from dataclasses import dataclass, field

from bibtexparser.model import Entry, Field

from biblio.bibliography import Bibliography
from biblio.results import ChangeSet, FieldDelta

_ALIASES = (("archiveprefix", "eprinttype"), ("primaryclass", "eprintclass"))


@dataclass(frozen=True, slots=True)
class EprintNormalizationReport:
    """Summary of alias migration, canonical spelling, and preserved conflicts."""

    renamed_type: tuple[str, ...] = ()
    renamed_class: tuple[str, ...] = ()
    normalized_type: tuple[str, ...] = ()
    conflicts: tuple[tuple[str, str, str], ...] = ()
    changes: ChangeSet = field(default_factory=ChangeSet)


def normalize_eprint_fields(bibliography: Bibliography) -> EprintNormalizationReport:
    """Migrate nonconflicting aliases without inferring an entry's type."""
    renamed_type: list[str] = []
    renamed_class: list[str] = []
    normalized_type: list[str] = []
    conflicts: list[tuple[str, str, str]] = []
    deltas: list[FieldDelta] = []

    for entry in bibliography:
        fields = {item.key.casefold(): item for item in entry.fields}
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

    changed = set(renamed_type + renamed_class + normalized_type)
    changes = ChangeSet(
        tuple(entry.key for entry in bibliography if entry.key in changed), tuple(deltas)
    )
    return EprintNormalizationReport(
        tuple(renamed_type), tuple(renamed_class), tuple(normalized_type), tuple(conflicts), changes
    )


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

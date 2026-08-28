"""Lossless migration of the explicitly accepted MR journal-pair convention."""

from dataclasses import dataclass, field

from bibtexparser.model import Entry, Field

from biblio.bibliography import Bibliography
from biblio.results import ChangeSet, FieldDelta

from .mr import MR_FIELDS, has_mr_metadata

LEGACY_JOURNAL_FIELD_MAP = (
    ("journal", "shortjournal"),
    ("fjournal", "journaltitle"),
)
_PARTICIPATING_FIELDS = MR_FIELDS | frozenset(
    name for pair in LEGACY_JOURNAL_FIELD_MAP for name in pair
)


@dataclass(frozen=True, slots=True)
class JournalNormalizationReport:
    """Journal-pair changes plus incomplete pairs and conflicts requiring review."""

    conflicts: tuple[tuple[str, str, str], ...] = ()
    ambiguous: tuple[tuple[str, str, str], ...] = ()
    changes: ChangeSet = field(default_factory=ChangeSet)


def normalize_journal_fields(bibliography: Bibliography) -> JournalNormalizationReport:
    """Migrate only an explicitly MR-marked nonempty pair without target conflicts.

    The accepted input convention supplies both ``journal`` (abbreviated title)
    and ``fjournal`` (full title), plus a nonempty local MR metadata marker.
    A lone field or unmarked pair does not establish that local convention.
    Check the whole pair before changing either source, and retain exact values.
    """
    changed_keys: list[str] = []
    conflicts: list[tuple[str, str, str]] = []
    ambiguous: list[tuple[str, str, str]] = []
    deltas: list[FieldDelta] = []
    entries = [(entry, _participating_fields(entry)) for entry in bibliography]

    for entry, fields in entries:
        sources = [
            (source, target) for source, target in LEGACY_JOURNAL_FIELD_MAP if source in fields
        ]
        if (
            not has_mr_metadata(entry)
            or len(sources) != 2
            or any(not str(fields[source].value).strip() for source, _ in sources)
        ):
            ambiguous.extend((entry.key, source, target) for source, target in sources)
            continue
        entry_conflicts = [
            (entry.key, source, target)
            for source, target in sources
            if target in fields and str(fields[source].value) != str(fields[target].value)
        ]
        if entry_conflicts:
            conflicts.extend(entry_conflicts)
            continue

        for source, target in sources:
            source_field = fields[source]
            source_value = str(source_field.value)
            deltas.append(FieldDelta(entry.key, source, source_value, None))
            if target in fields:
                entry.fields.remove(source_field)
            else:
                entry.fields[entry.fields.index(source_field)] = Field(target, source_field.value)
                deltas.append(FieldDelta(entry.key, target, None, source_value))
        changed_keys.append(entry.key)

    return JournalNormalizationReport(
        conflicts=tuple(conflicts),
        ambiguous=tuple(ambiguous),
        changes=ChangeSet(tuple(changed_keys), tuple(deltas)),
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

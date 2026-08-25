"""Lossless migration of legacy journal field names."""

from dataclasses import dataclass, field

from bibtexparser.model import Entry, Field

from biblio.bibliography import Bibliography
from biblio.results import ChangeSet, FieldDelta

LEGACY_JOURNAL_FIELD_MAP = (
    ("journal", "shortjournal"),
    ("fjournal", "journaltitle"),
)


@dataclass(frozen=True, slots=True)
class JournalNormalizationReport:
    """Journal-field changes plus value conflicts requiring review."""

    conflicts: tuple[tuple[str, str, str], ...] = ()
    ambiguous: tuple[tuple[str, str, str], ...] = ()
    changes: ChangeSet = field(default_factory=ChangeSet)


def normalize_journal_fields(bibliography: Bibliography) -> JournalNormalizationReport:
    """Rename legacy journal fields unless a target has a different value."""
    changed_keys: list[str] = []
    conflicts: list[tuple[str, str, str]] = []
    ambiguous: list[tuple[str, str, str]] = []
    deltas: list[FieldDelta] = []

    for entry in bibliography:
        entry_changed = False
        for source, target in LEGACY_JOURNAL_FIELD_MAP:
            if source == "journal" and _journal_is_ambiguous(entry):
                ambiguous.append((entry.key, source, target))
                continue
            outcome = _migrate_field(entry, source, target)
            if outcome is None:
                continue
            if outcome == ():
                conflicts.append((entry.key, source, target))
                continue
            entry_changed = True
            deltas.extend(outcome)
        if entry_changed:
            changed_keys.append(entry.key)

    return JournalNormalizationReport(
        conflicts=tuple(conflicts),
        ambiguous=tuple(ambiguous),
        changes=ChangeSet(tuple(changed_keys), tuple(deltas)),
    )


def _journal_is_ambiguous(entry: Entry) -> bool:
    fields = entry.fields_dict
    return "journal" in fields and "fjournal" not in fields and "shortjournal" not in fields


def _migrate_field(entry: Entry, source: str, target: str) -> tuple[FieldDelta, ...] | None:
    fields = entry.fields_dict
    source_field = fields.get(source)
    if source_field is None:
        return None

    source_value = str(source_field.value)
    target_field = fields.get(target)
    if target_field is not None and str(target_field.value) != source_value:
        return ()

    if target_field is None:
        replacement = Field(target, source_field.value)
        position = entry.fields.index(source_field)
        entry.fields[position] = replacement
        return (
            FieldDelta(entry.key, source, source_value, None),
            FieldDelta(entry.key, target, None, source_value),
        )

    entry.fields.remove(source_field)
    return (FieldDelta(entry.key, source, source_value, None),)

"""Pure normalization helpers for BibLaTeX date fields."""

from bibtexparser.model import Entry, Field

from biblio.bibliography import Bibliography
from biblio.results import ChangeSet, FieldDelta


def rename_year_to_date_fields(bibliography: Bibliography) -> ChangeSet:
    """Rename ``year`` to ``date`` when an entry has no ``date`` field."""
    changed_keys: list[str] = []
    deltas: list[FieldDelta] = []

    for entry in bibliography:
        year_value = _rename_year_field(entry)
        if year_value is None:
            continue
        changed_keys.append(entry.key)
        deltas.extend(
            (
                FieldDelta(entry.key, "year", year_value, None),
                FieldDelta(entry.key, "date", None, year_value),
            )
        )

    return ChangeSet(tuple(changed_keys), tuple(deltas))


def _rename_year_field(entry: Entry) -> str | None:
    """Rename one entry's ``year`` field and return its exact value."""
    fields = entry.fields_dict
    if "date" in fields or "year" not in fields:
        return None

    year_field = fields["year"]
    year_value = str(year_field.value)
    for index, field in enumerate(entry.fields):
        if field is year_field:
            entry.fields[index] = Field("date", year_field.value)
            break
    else:  # pragma: no cover - defensive against an inconsistent parser model
        entry.fields.append(Field("date", year_field.value))
    return year_value

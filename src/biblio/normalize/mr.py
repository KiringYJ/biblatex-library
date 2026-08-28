"""Explicit local MR metadata markers for source-convention-sensitive actions."""

from bibtexparser.model import Entry

MR_FIELDS = frozenset({"mrnumber", "mrclass", "mrreviewer"})


def has_mr_metadata(entry: Entry) -> bool:
    """Whether an exact MR marker field is nonempty, not a provenance verification."""
    return any(
        entry_field.key.casefold() in MR_FIELDS and bool(str(entry_field.value).strip())
        for entry_field in entry.fields
    )

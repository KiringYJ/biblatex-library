"""Deterministic whitespace normalization for BibLaTeX name lists."""

import re

from biblio.bibliography import Bibliography
from biblio.results import ChangeSet, FieldDelta

NAME_FIELDS = frozenset(
    {
        "afterword",
        "annotator",
        "author",
        "bookauthor",
        "commentator",
        "editor",
        "editora",
        "editorb",
        "editorc",
        "foreword",
        "holder",
        "introduction",
        "namea",
        "nameb",
        "namec",
        "shortauthor",
        "shorteditor",
        "sortname",
        "translator",
    }
)
_SPACE_BEFORE_COMMA = re.compile(r"[ \t]+,")


def normalize_name_value(value: str) -> str:
    """Remove horizontal whitespace immediately before name-part commas."""
    return _SPACE_BEFORE_COMMA.sub(",", value)


def normalize_name_spacing(bibliography: Bibliography) -> ChangeSet:
    """Normalize comma spacing in declared BibLaTeX name fields."""
    changed_keys: list[str] = []
    deltas: list[FieldDelta] = []

    for entry in bibliography:
        entry_changed = False
        for entry_field in entry.fields:
            field_name = entry_field.key.casefold()
            if field_name not in NAME_FIELDS:
                continue
            before = str(entry_field.value)
            after = normalize_name_value(before)
            if after == before:
                continue
            entry_field.value = after
            entry_changed = True
            deltas.append(FieldDelta(entry.key, entry_field.key, before, after))
        if entry_changed:
            changed_keys.append(entry.key)

    return ChangeSet(tuple(changed_keys), tuple(deltas))

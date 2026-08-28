"""Source-preserving whitespace normalization for plain BibLaTeX name lists."""

from biblio.bibliography import Bibliography
from biblio.results import ChangeSet, FieldDelta

from .tex import scan_text

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


def normalize_name_value(value: str) -> str:
    """Remove horizontal whitespace only before plain top-level name commas.

    Braced literal names and protected parts retain their exact spelling.
    Control sequences and extended/quoted name syntax make the field opaque.
    """
    tokens = scan_text(value)
    if tokens is None or any(token.kind == "command" for token in tokens):
        return value
    if '"' in value or "=" in value:
        return value
    removed: set[int] = set()
    for token in tokens:
        if token.kind != "character" or token.value != "," or token.depth != 0:
            continue
        position = token.start - 1
        while position >= 0 and value[position] in " \t":
            removed.add(position)
            position -= 1
    return "".join(character for index, character in enumerate(value) if index not in removed)


def normalize_name_spacing(bibliography: Bibliography) -> ChangeSet:
    """Normalize supported separator spacing only in declared name fields."""
    changed_keys: list[str] = []
    deltas: list[FieldDelta] = []
    for entry in bibliography:
        entry_changed = False
        for entry_field in entry.fields:
            if entry_field.key.casefold() not in NAME_FIELDS:
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

"""Type stubs for bibtexparser.model module."""

from collections.abc import MutableMapping

class Field:
    """Represents a field in a BibTeX entry."""

    value: str
    def __init__(self, value: str) -> None: ...

class Entry:
    """Represents a BibTeX entry."""

    key: str
    entry_type: str
    fields_dict: MutableMapping[str, Field]

    def __init__(
        self, key: str, entry_type: str, fields_dict: MutableMapping[str, Field] | None = None
    ) -> None: ...

__all__ = ["Field", "Entry"]

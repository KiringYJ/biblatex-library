"""Type stubs for bibtexparser.model module."""

from collections.abc import MutableMapping
from typing import Any

class Field:
    """Represents a field in a BibTeX entry."""

    key: str
    value: str
    def __init__(self, key: str, value: Any, start_line: int | None = None) -> None: ...

class Entry:
    """Represents a BibTeX entry."""

    key: str
    entry_type: str
    fields: list[Field]
    fields_dict: MutableMapping[str, Field]

    def __init__(
        self, key: str, entry_type: str, fields_dict: MutableMapping[str, Field] | None = None
    ) -> None: ...

__all__ = ["Field", "Entry"]

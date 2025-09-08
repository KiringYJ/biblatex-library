"""Type stubs for bibtexparser.library module."""

from collections.abc import Sequence

from .model import Entry

Block = Entry | str  # Simplified - could be other types

class Library:
    """Represents a BibTeX library/database."""

    entries: Sequence[Entry]
    blocks: Sequence[Block]
    failed_blocks: Sequence[Block]

    def __init__(self, blocks: Sequence[Block] | None = None) -> None: ...
    def add(self, entry: Entry) -> None: ...
    def remove(self, entry: Entry) -> None: ...

__all__ = ["Library", "Block"]

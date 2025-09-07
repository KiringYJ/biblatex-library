"""Type definitions for biblib data structures."""

from typing import TypedDict


class IdentifierData(TypedDict):
    """Structure for identifier data entries."""

    main_identifier: str
    identifiers: dict[str, str]


class EntryIdentifierData(TypedDict):
    """Structure for entry identifier data in JSON files."""

    main_identifier: str
    identifiers: dict[str, str]


# Type aliases for common data structures
IdentifierCollection = dict[str, IdentifierData]
AddOrderList = list[str]
KeyMapping = dict[str, str]

"""JSON validation utilities using msgspec for type-safe data loading."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import msgspec

from .types import AddOrderList, IdentifierCollection, IdentifierData


def validate_add_order_list(data: Any) -> AddOrderList:
    """Validate JSON data as AddOrderList with msgspec.

    Args:
        data: Raw JSON data (from json.load)

    Returns:
        Validated list of strings

    Raises:
        ValueError: If data doesn't match schema
    """
    try:
        return msgspec.convert(data, type=list[str])
    except msgspec.ValidationError as e:
        raise ValueError(str(e)) from e


def validate_identifier_data(data: Any) -> IdentifierData:
    """Validate JSON data as IdentifierData with msgspec.

    Args:
        data: Raw JSON data (from json.load)

    Returns:
        Validated IdentifierData struct

    Raises:
        ValueError: If data doesn't match schema
    """
    try:
        return msgspec.convert(data, type=IdentifierData)
    except msgspec.ValidationError as e:
        raise ValueError(str(e)) from e


def validate_identifier_collection(data: Any) -> IdentifierCollection:
    """Validate JSON data as IdentifierCollection with msgspec.

    Args:
        data: Raw JSON data (from json.load)

    Returns:
        Validated mapping of citekeys to IdentifierData

    Raises:
        ValueError: If data doesn't match schema
    """
    try:
        return msgspec.convert(data, type=dict[str, IdentifierData])
    except msgspec.ValidationError as e:
        raise ValueError(str(e)) from e


# Convenience functions for file loading
def load_add_order_list(path: Path) -> AddOrderList:
    """Load and validate add_order.json file."""
    with open(path, "rb") as f:
        return msgspec.json.decode(f.read(), type=list[str])


def load_identifier_collection(path: Path) -> IdentifierCollection:
    """Load and validate identifier_collection.json file."""
    with open(path, "rb") as f:
        return msgspec.json.decode(f.read(), type=dict[str, IdentifierData])

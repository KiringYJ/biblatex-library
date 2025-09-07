"""JSON validation utilities for type-safe data loading."""

from typing import Any

from .types import AddOrderList, IdentifierCollection, IdentifierData


def validate_add_order_list(data: Any) -> AddOrderList:
    """Validate JSON data as AddOrderList with complete type checking."""
    if not isinstance(data, list):
        raise ValueError(f"Expected array, got {type(data).__name__}")

    # Validate each item is a string
    validated_items: list[str] = []
    for i, item in enumerate(data):
        if not isinstance(item, str):
            raise ValueError(f"Expected string at index {i}, got {type(item).__name__}")
        validated_items.append(item)

    return validated_items


def validate_identifier_data(data: Any, entry_key: str) -> IdentifierData:
    """Validate JSON data as IdentifierData with complete type checking."""
    if not isinstance(data, dict):
        raise ValueError(f"Expected object for entry '{entry_key}', got {type(data).__name__}")

    # Check required fields
    if "main_identifier" not in data:
        raise ValueError(f"Missing 'main_identifier' in entry '{entry_key}'")
    if not isinstance(data["main_identifier"], str):
        raise ValueError(f"Expected string 'main_identifier' in entry '{entry_key}'")

    if "identifiers" not in data:
        raise ValueError(f"Missing 'identifiers' in entry '{entry_key}'")
    if not isinstance(data["identifiers"], dict):
        raise ValueError(f"Expected object 'identifiers' in entry '{entry_key}'")

    # Validate identifiers dict
    validated_identifiers: dict[str, str] = {}
    for id_key, id_value in data["identifiers"].items():
        if not isinstance(id_key, str):
            raise ValueError(f"Expected string identifier key in entry '{entry_key}'")
        if not isinstance(id_value, str):
            raise ValueError(f"Expected string identifier value in entry '{entry_key}'")
        validated_identifiers[id_key] = id_value

    # Return properly typed IdentifierData
    validated_data: IdentifierData = {
        "main_identifier": data["main_identifier"],
        "identifiers": validated_identifiers,
    }
    return validated_data


def validate_identifier_collection(data: Any) -> IdentifierCollection:
    """Validate JSON data as IdentifierCollection with complete type checking."""
    if not isinstance(data, dict):
        raise ValueError(f"Expected object, got {type(data).__name__}")

    validated_collection: dict[str, IdentifierData] = {}
    for key, value in data.items():
        if not isinstance(key, str):
            raise ValueError(f"Expected string key, got {type(key).__name__}")

        # Validate each entry using the IdentifierData validator
        validated_entry = validate_identifier_data(value, key)
        validated_collection[key] = validated_entry

    return validated_collection

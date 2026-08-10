"""Normalization helpers for ISBN fields.

Converts ISBN-10 values to ISBN-13 format for consistency.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from biblio.bibliography import Bibliography
from biblio.identifiers import (
    calculate_isbn13_check_digit,
    extract_isbn_digits,
    is_valid_isbn10,
    is_valid_isbn13,
    isbn13_digits_from_isbn10,
)
from biblio.results import ChangeSet, FieldDelta

__all__ = [
    "IsbnNormalizationReport",
    "calculate_isbn13_check_digit",
    "convert_isbn10_to_isbn13",
    "extract_isbn_digits",
    "is_valid_isbn10",
    "is_valid_isbn13",
    "normalize_isbn_field",
    "normalize_isbn_fields",
]


@dataclass(frozen=True, slots=True)
class IsbnNormalizationReport:
    """Summary of ISBN field normalization."""

    converted: dict[str, tuple[str, ...]] = field(default_factory=dict)
    """Maps entry keys to list of converted ISBNs (old -> new)."""

    already_isbn13: tuple[str, ...] = ()
    """Entry keys that already had valid ISBN-13 values."""

    invalid: dict[str, str] = field(default_factory=dict)
    """Maps entry keys to invalid ISBN values that couldn't be converted."""

    changes: ChangeSet = field(default_factory=ChangeSet)

    @property
    def total_converted(self) -> int:
        """Total number of ISBNs converted."""
        return sum(len(v) for v in self.converted.values())


def convert_isbn10_to_isbn13(isbn10: str) -> str | None:
    """Convert an ISBN-10 to ISBN-13 format.

    Args:
        isbn10: ISBN-10 string (with or without hyphens)

    Returns:
        ISBN-13 string with hyphens, or None if invalid
    """
    isbn13_digits = isbn13_digits_from_isbn10(isbn10)
    if isbn13_digits is None:
        return None
    check_digit = isbn13_digits[-1]

    # Format with hyphens: 978-X-XXXX-XXXX-X
    # Standard format: 978-[registration group]-[registrant]-[publication]-[check]
    # For simplicity, use: 978-X-XXXX-XXXX-X pattern based on original ISBN-10
    # The hyphenation follows the original ISBN-10 pattern if available

    # Try to preserve original hyphenation pattern from ISBN-10
    original_parts = re.split(r"[-\s]", isbn10)
    if len(original_parts) >= 4:
        # Original had hyphens, try to preserve structure
        # ISBN-10: group-registrant-publication-check
        # ISBN-13: 978-group-registrant-publication-check
        return f"978-{original_parts[0]}-{original_parts[1]}-{original_parts[2]}-{check_digit}"

    # Fallback: just return as contiguous digits
    return isbn13_digits


def normalize_isbn_field(isbn_value: str) -> tuple[str, list[str]]:
    """Normalize an ISBN field value, converting any ISBN-10s to ISBN-13.

    Handles fields with multiple ISBNs separated by commas.

    Args:
        isbn_value: Raw ISBN field value (may contain multiple ISBNs)

    Returns:
        Tuple of (normalized_value, list_of_conversions)
        where list_of_conversions contains "old -> new" strings
    """
    # Split by comma to handle multiple ISBNs
    parts = [p.strip() for p in isbn_value.split(",")]
    normalized_parts: list[str] = []
    seen_digits: set[str] = set()
    conversions: list[str] = []

    for part in parts:
        if not part:
            continue

        digits = extract_isbn_digits(part)

        if len(digits) == 13 and is_valid_isbn13(digits):
            # Already ISBN-13, keep original formatting (deduplicate)
            if digits not in seen_digits:
                normalized_parts.append(part)
                seen_digits.add(digits)
        elif len(digits) == 10:
            # Try to convert ISBN-10 to ISBN-13
            converted = convert_isbn10_to_isbn13(part)
            if converted:
                converted_digits = extract_isbn_digits(converted)
                if converted_digits not in seen_digits:
                    conversions.append(f"{part} → {converted}")
                    normalized_parts.append(converted)
                    seen_digits.add(converted_digits)
                else:
                    # Converted ISBN-13 already present; drop the duplicate
                    conversions.append(f"{part} → (deduplicated)")
            else:
                # Invalid ISBN-10, keep original
                normalized_parts.append(part)
        else:
            # Unknown format, keep original
            normalized_parts.append(part)

    return ", ".join(normalized_parts), conversions


def normalize_isbn_fields(
    bibliography: Bibliography,
) -> IsbnNormalizationReport:
    """Normalize in-memory ISBN fields, converting ISBN-10 to ISBN-13."""
    converted: dict[str, tuple[str, ...]] = {}
    already_isbn13: list[str] = []
    invalid: dict[str, str] = {}
    deltas: list[FieldDelta] = []

    for entry in bibliography:
        fields = entry.fields_dict
        isbn_field = fields.get("isbn")

        if isbn_field is None:
            continue

        isbn_value = str(isbn_field.value).strip()
        if not isbn_value:
            continue

        # Normalize the ISBN field (converts ISBN-10 to ISBN-13 and deduplicates)
        normalized_value, conversions = normalize_isbn_field(isbn_value)

        if conversions:
            converted[entry.key] = tuple(conversions)
            isbn_field.value = normalized_value
            deltas.append(FieldDelta(entry.key, "isbn", isbn_value, normalized_value))
        elif normalized_value != isbn_value:
            converted[entry.key] = (f"deduplicated: {isbn_value} → {normalized_value}",)
            isbn_field.value = normalized_value
            deltas.append(FieldDelta(entry.key, "isbn", isbn_value, normalized_value))
        else:
            digits = extract_isbn_digits(isbn_value)
            if len(digits) == 13 and is_valid_isbn13(digits):
                already_isbn13.append(entry.key)
            else:
                invalid[entry.key] = isbn_value

    changes = ChangeSet(tuple(converted), tuple(deltas))
    return IsbnNormalizationReport(converted, tuple(already_isbn13), invalid, changes)

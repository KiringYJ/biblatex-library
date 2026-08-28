"""Conservative normalization of bare, checksum-valid ISBN lists."""

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

_BARE_ISBN = re.compile(r"[0-9]+(?:[- ][0-9]+)*(?:[- ]?[Xx])?")


@dataclass(frozen=True, slots=True)
class IsbnNormalizationReport:
    """Summary of ISBN field normalization."""

    converted: dict[str, tuple[str, ...]] = field(default_factory=dict)
    """Maps entry keys to conversions or duplicate removals."""

    already_isbn13: tuple[str, ...] = ()
    """Entry keys containing only valid ISBN-13 values without changes."""

    invalid: dict[str, str] = field(default_factory=dict)
    """Exact values preserved because at least one token is unsupported."""

    changes: ChangeSet = field(default_factory=ChangeSet)

    @property
    def total_converted(self) -> int:
        """Total number of reported conversions or duplicate removals."""
        return sum(len(value) for value in self.converted.values())


def convert_isbn10_to_isbn13(isbn10: str) -> str | None:
    """Convert a bare ISBN-10 to contiguous ISBN-13 digits without guessing groups."""
    if _BARE_ISBN.fullmatch(isbn10) is None:
        return None
    return isbn13_digits_from_isbn10(isbn10)


def _validated_parts(value: str) -> list[tuple[str, str]] | None:
    parts: list[tuple[str, str]] = []
    for token in value.split(","):
        part = token.strip(" \t\r\n")
        if _BARE_ISBN.fullmatch(part) is None:
            return None
        digits = extract_isbn_digits(part)
        if not (
            is_valid_isbn10(digits)
            or (digits.startswith(("978", "979")) and is_valid_isbn13(digits))
        ):
            return None
        parts.append((part, digits))
    return parts


def normalize_isbn_field(isbn_value: str) -> tuple[str, list[str]]:
    """Convert and deduplicate only wholly validated comma-separated bare ISBNs.

    An unsupported token preserves the entire original field byte-for-byte.
    Valid ISBN-13 formatting is retained; ISBN-10 conversion never reconstructs
    registration groups.
    """
    parts = _validated_parts(isbn_value)
    if parts is None:
        return isbn_value, []

    normalized_parts: list[str] = []
    seen_digits: set[str] = set()
    conversions: list[str] = []
    deduplicated = False
    for part, digits in parts:
        converted = isbn13_digits_from_isbn10(digits)
        canonical = converted if converted is not None else digits
        if canonical in seen_digits:
            deduplicated = True
            if converted is not None:
                conversions.append(f"{part} → (deduplicated)")
            continue
        seen_digits.add(canonical)
        if converted is not None:
            conversions.append(f"{part} → {converted}")
        normalized_parts.append(converted if converted is not None else part)
    if not conversions and not deduplicated:
        return isbn_value, []
    return ", ".join(normalized_parts), conversions


def normalize_isbn_fields(bibliography: Bibliography) -> IsbnNormalizationReport:
    """Normalize in-memory ISBN fields only after whole-field validation."""
    converted: dict[str, tuple[str, ...]] = {}
    already_isbn13: list[str] = []
    invalid: dict[str, str] = {}
    deltas: list[FieldDelta] = []

    for entry in bibliography:
        isbn_field = next((item for item in entry.fields if item.key.casefold() == "isbn"), None)
        if isbn_field is None:
            continue
        isbn_value = str(isbn_field.value)
        if _validated_parts(isbn_value) is None:
            invalid[entry.key] = isbn_value
            continue
        normalized_value, conversions = normalize_isbn_field(isbn_value)
        if normalized_value != isbn_value:
            converted[entry.key] = tuple(conversions) or (
                f"deduplicated: {isbn_value} → {normalized_value}",
            )
            isbn_field.value = normalized_value
            deltas.append(FieldDelta(entry.key, "isbn", isbn_value, normalized_value))
        else:
            already_isbn13.append(entry.key)

    changes = ChangeSet(tuple(converted), tuple(deltas))
    return IsbnNormalizationReport(converted, tuple(already_isbn13), invalid, changes)

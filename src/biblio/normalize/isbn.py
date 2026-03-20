"""Normalization helpers for ISBN fields.

Converts ISBN-10 values to ISBN-13 format for consistency.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import bibtexparser
from bibtexparser.library import Library

logger = logging.getLogger(__name__)

# Pattern to extract digits/X from ISBN strings
ISBN_DIGIT_PATTERN = re.compile(r"[\dXx]")


@dataclass(slots=True)
class IsbnNormalizationReport:
    """Summary of ISBN field normalization."""

    converted: dict[str, list[str]] = field(default_factory=lambda: {})
    """Maps entry keys to list of converted ISBNs (old -> new)."""

    already_isbn13: list[str] = field(default_factory=lambda: [])
    """Entry keys that already had valid ISBN-13 values."""

    invalid: dict[str, str] = field(default_factory=lambda: {})
    """Maps entry keys to invalid ISBN values that couldn't be converted."""

    identifier_converted: dict[str, str] = field(default_factory=lambda: {})
    """Maps entry keys to converted isbn13 values in identifier_collection."""

    @property
    def total_converted(self) -> int:
        """Total number of ISBNs converted."""
        return sum(len(v) for v in self.converted.values())


def extract_isbn_digits(isbn_str: str) -> str:
    """Extract only digits and X from an ISBN string.

    Args:
        isbn_str: Raw ISBN string (may contain hyphens, spaces, etc.)

    Returns:
        String containing only digits and X characters
    """
    return "".join(ISBN_DIGIT_PATTERN.findall(isbn_str)).upper()


def is_valid_isbn10(digits: str) -> bool:
    """Check if a 10-digit string is a valid ISBN-10.

    Args:
        digits: 10 character string of digits (last may be X)

    Returns:
        True if valid ISBN-10
    """
    if len(digits) != 10:
        return False

    total = 0
    for i, char in enumerate(digits):
        if char == "X":
            if i != 9:  # X only allowed as check digit
                return False
            value = 10
        elif char.isdigit():
            value = int(char)
        else:
            return False
        total += value * (10 - i)

    return total % 11 == 0


def is_valid_isbn13(digits: str) -> bool:
    """Check if a 13-digit string is a valid ISBN-13.

    Args:
        digits: 13 character string of digits

    Returns:
        True if valid ISBN-13
    """
    if len(digits) != 13 or not digits.isdigit():
        return False

    total = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(digits))
    return total % 10 == 0


def calculate_isbn13_check_digit(first_12: str) -> str:
    """Calculate the check digit for ISBN-13.

    Args:
        first_12: First 12 digits of the ISBN-13

    Returns:
        Single digit character (0-9)
    """
    total = sum(int(d) * (1 if i % 2 == 0 else 3) for i, d in enumerate(first_12))
    check = (10 - (total % 10)) % 10
    return str(check)


def convert_isbn10_to_isbn13(isbn10: str) -> str | None:
    """Convert an ISBN-10 to ISBN-13 format.

    Args:
        isbn10: ISBN-10 string (with or without hyphens)

    Returns:
        ISBN-13 string with hyphens, or None if invalid
    """
    digits = extract_isbn_digits(isbn10)

    if not is_valid_isbn10(digits):
        return None

    # Take first 9 digits, prepend 978
    isbn13_base = "978" + digits[:9]
    check_digit = calculate_isbn13_check_digit(isbn13_base)
    isbn13_digits = isbn13_base + check_digit

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
    library_path: Path,
    identifier_path: Path | None = None,
    *,
    dry_run: bool = False,
) -> IsbnNormalizationReport:
    """Normalize ISBN fields in a bib file, converting ISBN-10 to ISBN-13.

    Also normalizes ``isbn13`` values in *identifier_collection.json* when
    *identifier_path* is provided.

    Args:
        library_path: Path to ``library.bib``
        identifier_path: Optional path to ``identifier_collection.json``
        dry_run: When ``True``, report changes without writing to disk

    Returns:
        :class:`IsbnNormalizationReport` describing applied changes

    Raises:
        FileNotFoundError: If ``library_path`` does not exist
        ValueError: If the bib file cannot be parsed
    """
    if not library_path.exists():
        raise FileNotFoundError(f"Bibliography file not found: {library_path}")

    logger.debug("Loading library for ISBN normalization: %s", library_path)

    try:
        library: Library = bibtexparser.parse_file(str(library_path))
    except Exception as exc:  # pragma: no cover - parser raises custom errors
        raise ValueError(f"Failed to parse {library_path}: {exc}") from exc

    report = IsbnNormalizationReport()
    modified = False

    for entry in library.entries:
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
            report.converted[entry.key] = conversions
            if not dry_run:
                isbn_field.value = normalized_value
                modified = True
            logger.debug(
                "Entry %s: converted %d ISBN(s): %s",
                entry.key,
                len(conversions),
                "; ".join(conversions),
            )
        elif normalized_value != isbn_value:
            # Deduplication occurred without ISBN-10 conversion
            report.converted[entry.key] = [f"deduplicated: {isbn_value} → {normalized_value}"]
            if not dry_run:
                isbn_field.value = normalized_value
                modified = True
            logger.debug(
                "Entry %s: deduplicated ISBN field: %s → %s",
                entry.key,
                isbn_value,
                normalized_value,
            )
        else:
            report.already_isbn13.append(entry.key)

    if not dry_run and modified:
        logger.debug("Writing ISBN normalization changes back to disk: %s", library_path)
        bibtex_string = bibtexparser.write_string(library)
        with open(library_path, "w", encoding="utf-8") as bib_file:
            bib_file.write(str(bibtex_string))

    # Normalize isbn13 values in identifier_collection.json
    if identifier_path is not None:
        _normalize_identifier_collection_isbns(identifier_path, report, dry_run=dry_run)

    return report


def _normalize_identifier_collection_isbns(
    identifier_path: Path,
    report: IsbnNormalizationReport,
    *,
    dry_run: bool = False,
) -> None:
    """Normalize isbn13 values in identifier_collection.json.

    Converts any ISBN-10 stored in the ``isbn13`` field to a proper
    de-hyphenated ISBN-13 value.

    Args:
        identifier_path: Path to ``identifier_collection.json``
        report: Report object to update with changes
        dry_run: When ``True``, report changes without writing to disk
    """
    if not identifier_path.exists():
        logger.warning("Identifier collection not found: %s", identifier_path)
        return

    with open(identifier_path, encoding="utf-8") as f:
        data: dict[str, object] = json.load(f)

    modified = False

    for key, entry_data in data.items():
        if not isinstance(entry_data, dict):
            continue
        identifiers = entry_data.get("identifiers")
        if not isinstance(identifiers, dict):
            continue

        isbn_value = identifiers.get("isbn13")
        if isbn_value is None or not isinstance(isbn_value, str):
            continue

        digits = extract_isbn_digits(isbn_value)

        # Already a valid ISBN-13
        if len(digits) == 13 and is_valid_isbn13(digits):
            continue

        # Attempt ISBN-10 → ISBN-13 conversion
        if len(digits) == 10 and is_valid_isbn10(digits):
            isbn13_base = "978" + digits[:9]
            check_digit = calculate_isbn13_check_digit(isbn13_base)
            new_value = isbn13_base + check_digit

            report.identifier_converted[key] = f"{isbn_value} → {new_value}"
            logger.debug("identifier_collection %s: isbn13 %s → %s", key, isbn_value, new_value)
            if not dry_run:
                identifiers["isbn13"] = new_value
                modified = True
        else:
            logger.warning("identifier_collection %s: invalid isbn13 value: %s", key, isbn_value)

    if not dry_run and modified:
        logger.debug("Writing isbn13 normalization changes to: %s", identifier_path)
        with open(identifier_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

"""Normalization helpers for LaTeX accent sequences."""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import bibtexparser
from bibtexparser.library import Library
from bibtexparser.model import Entry

logger = logging.getLogger(__name__)

_ACCENT_COMBINING = {
    "'": "\u0301",  # acute
    "`": "\u0300",  # grave
    '"': "\u0308",  # diaeresis
    "^": "\u0302",  # circumflex
    "~": "\u0303",  # tilde
    "=": "\u0304",  # macron
    ".": "\u0307",  # dot above
    "d": "\u0323",  # dot below
    "b": "\u0331",  # macron below
    "H": "\u030b",  # double acute
    "c": "\u0327",  # cedilla
    "k": "\u0328",  # ogonek
    "r": "\u030a",  # ring above
    "u": "\u0306",  # breve
    "v": "\u030c",  # caron
}

_ACCENT_COMMANDS = "".join(sorted(_ACCENT_COMBINING.keys()))

_BRACED_ACCENT_PATTERN = re.compile(
    rf"\{{\\([{_ACCENT_COMMANDS}])(?:\s*\{{([^{{}}]+)\}}|([A-Za-z]))\}}"
)

_ACCENT_PATTERN = re.compile(rf"\\([{_ACCENT_COMMANDS}])(?:\s*\{{([^{{}}]+)\}}|([A-Za-z]))")

_SPECIAL_BASE_MAP = {
    "\\i": "i",
    "\\j": "j",
}

_SPECIAL_MACROS = {
    "\\ae": "æ",
    "\\AE": "Æ",
    "\\oe": "œ",
    "\\OE": "Œ",
    "\\aa": "å",
    "\\AA": "Å",
    "\\ss": "ß",
    "\\o": "ø",
    "\\O": "Ø",
    "\\l": "ł",
    "\\L": "Ł",
}

_SINGLE_CHAR_NONASCII_BRACES = re.compile(r"\{([^{}])\}")


@dataclass(slots=True)
class AccentNormalizationReport:
    """Summary of LaTeX accent normalization."""

    converted: dict[str, list[str]]

    @property
    def total_fields(self) -> int:
        return sum(len(fields) for fields in self.converted.values())


def normalize_latex_accents(
    library_path: Path, *, dry_run: bool = False
) -> AccentNormalizationReport:
    """Convert LaTeX accent commands within field values to Unicode.

    Args:
        library_path: Path to ``library.bib``
        dry_run: When ``True``, preview planned changes without writing to disk

    Returns:
        :class:`AccentNormalizationReport` describing modified entries

    Raises:
        FileNotFoundError: If ``library_path`` does not exist
        ValueError: If the bib file cannot be parsed
    """
    if not library_path.exists():
        raise FileNotFoundError(f"Bibliography file not found: {library_path}")

    logger.debug("Loading library for accent normalization: %s", library_path)

    try:
        library: Library = bibtexparser.parse_file(str(library_path))
    except Exception as exc:  # pragma: no cover - parser raises custom errors
        raise ValueError(f"Failed to parse {library_path}: {exc}") from exc

    converted: dict[str, list[str]] = {}

    for entry in library.entries:
        changed_fields = _normalize_entry(entry, dry_run=dry_run)
        if changed_fields:
            converted[entry.key] = changed_fields

    if converted and not dry_run:
        logger.debug("Writing accent normalization changes back to disk: %s", library_path)
        bibtex_string = bibtexparser.write_string(library)
        with open(library_path, "w", encoding="utf-8") as bib_file:
            bib_file.write(str(bibtex_string))

    return AccentNormalizationReport(converted=converted)


def _normalize_entry(entry: Entry, *, dry_run: bool) -> list[str]:
    changed: list[str] = []

    for field in entry.fields:
        value = str(field.value)
        normalized = _convert_value(value)
        if normalized == value:
            continue

        logger.info(
            "Converted LaTeX accents for %s.%s: '%s' -> '%s'",
            entry.key,
            field.key,
            value,
            normalized,
        )
        changed.append(field.key)

        if not dry_run:
            field.value = normalized

    return changed


def _convert_value(value: str) -> str:
    if "\\" not in value:
        return value

    updated = _BRACED_ACCENT_PATTERN.sub(_replace_accent, value)
    updated = _ACCENT_PATTERN.sub(_replace_accent, updated)
    updated = _replace_special_macros(updated)
    updated = _strip_nonascii_single_braces(updated)
    return updated


def _replace_accent(match: re.Match[str]) -> str:
    accent = match.group(1)
    target = match.group(2) or match.group(3)

    if target is None:
        return match.group(0)

    base = _resolve_base(target)
    if base is None:
        return match.group(0)

    combining = _ACCENT_COMBINING.get(accent)
    if combining is None:
        return match.group(0)

    composed = unicodedata.normalize("NFC", base + combining)
    return composed


def _resolve_base(raw: str) -> str | None:
    candidate = raw.strip()
    if not candidate:
        return None

    if candidate in _SPECIAL_BASE_MAP:
        return _SPECIAL_BASE_MAP[candidate]

    if len(candidate) == 1:
        return candidate

    return None


def _replace_special_macros(value: str) -> str:
    updated = value
    for macro, replacement in _SPECIAL_MACROS.items():
        if f"{macro}{{}}" in updated:
            updated = updated.replace(f"{macro}{{}}", replacement)
        if f"{{{macro}}}" in updated:
            updated = updated.replace(f"{{{macro}}}", replacement)
        if macro in updated:
            updated = updated.replace(macro, replacement)
    return updated


def _strip_nonascii_single_braces(value: str) -> str:
    def _strip(match: re.Match[str]) -> str:
        char = match.group(1)
        if ord(char) > 127:
            return char
        return match.group(0)

    return _SINGLE_CHAR_NONASCII_BRACES.sub(_strip, value)

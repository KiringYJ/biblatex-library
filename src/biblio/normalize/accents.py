"""Normalization helpers for LaTeX text sequences."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from bibtexparser.model import Entry

from biblio.bibliography import Bibliography
from biblio.results import ChangeSet, FieldDelta

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

_SPECIAL_BASE_MAP = {
    "\\i": "i",
    "\\j": "j",
}
_SPECIAL_BASE_TARGET_PATTERN = (
    rf"(?:{'|'.join(re.escape(target) for target in _SPECIAL_BASE_MAP)})(?![A-Za-z@])"
)

# Split accent commands by type.  Letter accent commands (\r, \u, \v, ...)
# followed directly by a letter are ambiguous with LaTeX font/control commands
# (\rm, \bf, ...).  We require whitespace before a bare letter target for
# letter accent commands to avoid false matches.
_SYMBOL_ACCENT_CHARS = "".join(sorted(c for c in _ACCENT_COMBINING if not c.isalpha()))
_LETTER_ACCENT_CHARS = "".join(sorted(c for c in _ACCENT_COMBINING if c.isalpha()))
_SYMBOL_ACCENT_TARGET_PATTERN = rf"([A-Za-z]|{_SPECIAL_BASE_TARGET_PATTERN})"
_LETTER_ACCENT_TARGET_PATTERN = rf"(\s+[A-Za-z]|{_SPECIAL_BASE_TARGET_PATTERN})"

_BRACED_SYMBOL_ACCENT_RE = re.compile(
    rf"\{{\\([{_SYMBOL_ACCENT_CHARS}])"
    rf"(?:\s*\{{([^{{}}]+)\}}|{_SYMBOL_ACCENT_TARGET_PATTERN})\}}"
)
_BRACED_LETTER_ACCENT_RE = re.compile(
    rf"\{{\\([{_LETTER_ACCENT_CHARS}])"
    rf"(?:\s*\{{([^{{}}]+)\}}|{_LETTER_ACCENT_TARGET_PATTERN})\}}"
)

_SYMBOL_ACCENT_RE = re.compile(
    rf"\\([{_SYMBOL_ACCENT_CHARS}])"
    rf"(?:\s*\{{([^{{}}]+)\}}|{_SYMBOL_ACCENT_TARGET_PATTERN})"
)
_LETTER_ACCENT_RE = re.compile(
    rf"\\([{_LETTER_ACCENT_CHARS}])"
    rf"(?:\s*\{{([^{{}}]+)\}}|{_LETTER_ACCENT_TARGET_PATTERN})"
)

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

# Identifier values and the fields that type them are opaque. Their exact bytes
# may carry equality and historical citekey provenance outside this normalizer.
_IDENTIFIER_FIELDS = frozenset(
    {
        "acmdl_doi",
        "archiveprefix",
        "doi",
        "eprint",
        "eprintclass",
        "eprinttype",
        "hdl",
        "ids",
        "isbn",
        "isbn13",
        "jfm",
        "mrnumber",
        "oclc",
        "primaryclass",
        "url",
        "zbl",
        "zbmath",
    }
)


@dataclass(frozen=True, slots=True)
class AccentNormalizationReport:
    """Summary of LaTeX text normalization."""

    converted: dict[str, tuple[str, ...]]
    changes: ChangeSet = field(default_factory=ChangeSet)

    @property
    def total_fields(self) -> int:
        return sum(len(fields) for fields in self.converted.values())


def normalize_latex_accents(
    bibliography: Bibliography,
) -> AccentNormalizationReport:
    """Normalize LaTeX accents and ``mrreviewer`` control spaces in memory."""
    converted: dict[str, tuple[str, ...]] = {}
    deltas: list[FieldDelta] = []

    for entry in bibliography:
        entry_deltas = _normalize_entry(entry)
        changed_fields = tuple(delta.field for delta in entry_deltas)
        if changed_fields:
            converted[entry.key] = changed_fields
            deltas.extend(entry_deltas)

    changes = ChangeSet(tuple(converted), tuple(deltas))
    return AccentNormalizationReport(converted, changes)


def _normalize_entry(entry: Entry) -> list[FieldDelta]:
    changed: list[FieldDelta] = []

    for entry_field in entry.fields:
        field_name = entry_field.key.casefold()
        if field_name in _IDENTIFIER_FIELDS:
            continue
        value = str(entry_field.value)
        normalized = value
        if field_name == "mrreviewer":
            normalized = normalized.replace("\\ ", " ")
        normalized = _convert_value(normalized)
        if normalized == value:
            continue

        changed.append(FieldDelta(entry.key, entry_field.key, value, normalized))
        entry_field.value = normalized

    return changed


def _convert_value(value: str) -> str:
    if "\\" not in value:
        return value

    updated = _BRACED_SYMBOL_ACCENT_RE.sub(_replace_accent, value)
    updated = _BRACED_LETTER_ACCENT_RE.sub(_replace_accent, updated)
    updated = _SYMBOL_ACCENT_RE.sub(_replace_accent, updated)
    updated = _LETTER_ACCENT_RE.sub(_replace_accent, updated)
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

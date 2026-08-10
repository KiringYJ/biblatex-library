"""Pure identifier canonicalization, hashing, and classification primitives."""

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import unquote_to_bytes, urlsplit

_DOI_RESOLVER_HOSTS = frozenset({"doi.org", "www.doi.org", "dx.doi.org"})
_ASCII_UPPERCASE = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_ASCII_LOWERCASE = "abcdefghijklmnopqrstuvwxyz"
_ASCII_LOWERCASE_TRANSLATION = str.maketrans(_ASCII_UPPERCASE, _ASCII_LOWERCASE)
_INVALID_PERCENT_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})")
_DERIVED_ARXIV_DOI_PREFIX = "10.48550/arxiv."
_ISBN_DIGIT_PATTERN = re.compile(r"[\dXx]")


@dataclass(frozen=True, slots=True)
class CanonicalDoi:
    """Canonical wrapper-free DOI plus stripped resolver-component diagnostics."""

    value: str
    had_query: bool = False
    had_fragment: bool = False


def _validate_doi_name(name: str) -> str:
    if not name:
        raise ValueError("DOI name must not be empty")
    if not name.startswith("10."):
        raise ValueError("DOI name must start with '10.'")

    slash_position = name.find("/")
    if slash_position < 0:
        raise ValueError("DOI name must contain a first slash")
    if slash_position == len("10."):
        raise ValueError("DOI name must have a nonempty registrant segment")
    if slash_position == len(name) - 1:
        raise ValueError("DOI name must have a nonempty suffix")
    if any(unicodedata.category(character) == "Cc" for character in name):
        raise ValueError("DOI name must not contain control characters")
    return name.translate(_ASCII_LOWERCASE_TRANSLATION)


def _decode_resolver_path(path: str) -> str:
    if _INVALID_PERCENT_ESCAPE.search(path):
        raise ValueError("DOI resolver path contains an invalid percent escape")
    encoded_name = path[1:] if path.startswith("/") else path
    try:
        return unquote_to_bytes(encoded_name).decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ValueError("DOI resolver path is not valid UTF-8") from error


def _canonicalize_doi(raw: str) -> CanonicalDoi:
    trimmed = raw.strip()
    if not trimmed:
        raise ValueError("DOI name must not be empty")

    if trimmed[:4].casefold() == "doi:":
        name = trimmed[4:].strip()
        if "?" in name or "#" in name:
            raise ValueError("doi: DOI names must not contain query or fragment components")
        return CanonicalDoi(value=_validate_doi_name(name))

    if "://" not in trimmed:
        return CanonicalDoi(value=_validate_doi_name(trimmed))

    parsed = urlsplit(trimmed)
    if parsed.scheme.casefold() not in {"http", "https"}:
        raise ValueError("DOI resolver URL must use HTTP or HTTPS")
    if "@" in parsed.netloc or ":" in parsed.netloc:
        raise ValueError("DOI resolver URL must not contain userinfo or a port")
    if parsed.netloc.casefold() not in _DOI_RESOLVER_HOSTS:
        raise ValueError("DOI resolver URL must use an approved DOI resolver host")

    name = _decode_resolver_path(parsed.path)
    return CanonicalDoi(
        value=_validate_doi_name(name),
        had_query="?" in trimmed,
        had_fragment="#" in trimmed,
    )


def canonicalize_new_doi(raw: str) -> CanonicalDoi:
    """Canonicalize a DOI supplied for a new addition or promotion."""
    return _canonicalize_doi(raw)


def legacy_doi_comparison_token(raw: str) -> str:
    """Return a comparison token without modifying the exact legacy value."""
    return _canonicalize_doi(raw).value


def hash_exact_legacy_identifier(exact_value: str) -> str:
    """Hash exact historical UTF-8 bytes and return the legacy 8-hex suffix."""
    return hashlib.sha256(exact_value.encode("utf-8")).hexdigest()[:8]


def hash_canonical_new_doi(canonical_doi: CanonicalDoi) -> str:
    """Hash the canonical wrapper-free DOI UTF-8 bytes for a new citekey."""
    return hashlib.sha256(canonical_doi.value.encode("utf-8")).hexdigest()[:8]


def extract_isbn_digits(raw: str) -> str:
    """Return the ISBN digits and possible ISBN-10 check ``X`` from *raw*."""
    return "".join(_ISBN_DIGIT_PATTERN.findall(raw)).upper()


def is_valid_isbn10(digits: str) -> bool:
    """Return whether *digits* is a checksum-valid ISBN-10."""
    if len(digits) != 10:
        return False
    total = 0
    for index, character in enumerate(digits):
        if character == "X":
            if index != 9:
                return False
            value = 10
        elif character.isdigit():
            value = int(character)
        else:
            return False
        total += value * (10 - index)
    return total % 11 == 0


def is_valid_isbn13(digits: str) -> bool:
    """Return whether *digits* is a checksum-valid ISBN-13."""
    if len(digits) != 13 or not digits.isdigit():
        return False
    total = sum(
        int(character) * (1 if index % 2 == 0 else 3) for index, character in enumerate(digits)
    )
    return total % 10 == 0


def calculate_isbn13_check_digit(first_twelve: str) -> str:
    """Return the ISBN-13 check digit for exactly twelve decimal digits."""
    if len(first_twelve) != 12 or not first_twelve.isdigit():
        raise ValueError("ISBN-13 check-digit input must contain exactly twelve digits")
    total = sum(
        int(character) * (1 if index % 2 == 0 else 3)
        for index, character in enumerate(first_twelve)
    )
    return str((10 - (total % 10)) % 10)


def isbn13_digits_from_isbn10(raw: str) -> str | None:
    """Return canonical ISBN-13 digits for a valid ISBN-10, otherwise ``None``."""
    digits = extract_isbn_digits(raw)
    if not is_valid_isbn10(digits):
        return None
    first_twelve = "978" + digits[:9]
    return first_twelve + calculate_isbn13_check_digit(first_twelve)


def isbn_comparison_token(raw: str) -> str:
    """Compare valid ISBN-10 and ISBN-13 manifestations as one ISBN-13 value."""
    digits = extract_isbn_digits(raw)
    converted = isbn13_digits_from_isbn10(digits)
    if converted is not None:
        return converted
    if is_valid_isbn13(digits):
        return digits
    return raw.strip().replace("-", "").replace(" ", "").upper()


def _arxiv_comparison_token(raw: str) -> str:
    token = raw.strip()
    if token[:6].casefold() == "arxiv:":
        token = token[6:].strip()
    return token.casefold()


def is_derived_arxiv_doi(doi: str | CanonicalDoi, eprint: str) -> bool:
    """Return whether *doi* is the DataCite DOI derived from *eprint*."""
    doi_value = doi.value if isinstance(doi, CanonicalDoi) else doi.strip()
    normalized_doi = doi_value.translate(_ASCII_LOWERCASE_TRANSLATION)
    if not normalized_doi.startswith(_DERIVED_ARXIV_DOI_PREFIX):
        return False

    doi_eprint = normalized_doi[len(_DERIVED_ARXIV_DOI_PREFIX) :]
    eprint_token = _arxiv_comparison_token(eprint)
    return bool(doi_eprint and eprint_token and doi_eprint.casefold() == eprint_token)

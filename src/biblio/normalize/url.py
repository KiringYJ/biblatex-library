"""Normalization helpers for redundant identifier URL fields."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import bibtexparser
from bibtexparser.library import Library

logger = logging.getLogger(__name__)

_DOI_URL_PREFIXES = (
    "https://doi.org/",
    "http://doi.org/",
    "https://dx.doi.org/",
    "http://dx.doi.org/",
)
_ARXIV_URL_HOSTS = {"arxiv.org", "www.arxiv.org"}


@dataclass(slots=True)
class UrlNormalizationReport:
    """Summary of trivial URL removal."""

    removed: list[str]


def normalize_trivial_urls(library_path: Path, *, dry_run: bool = False) -> UrlNormalizationReport:
    """Remove URL fields that duplicate an explicit DOI or arXiv eprint.

    A URL is redundant when it matches ``https://doi.org/{doi}`` (or an
    ``http`` / ``dx.doi.org`` variant), or when a canonical arXiv abstract or
    PDF URL contains the same identifier as an explicit arXiv ``eprint``.
    BibLaTeX can construct links from those identifier fields, so retaining
    the URL adds no information.

    Args:
        library_path: Path to ``library.bib``
        dry_run: When ``True``, report changes without writing to disk

    Returns:
        :class:`UrlNormalizationReport` describing removed entries

    Raises:
        FileNotFoundError: If ``library_path`` does not exist
        ValueError: If the bib file cannot be parsed
    """
    if not library_path.exists():
        raise FileNotFoundError(f"Bibliography file not found: {library_path}")

    logger.debug("Loading library for trivial-URL normalization: %s", library_path)

    try:
        library: Library = bibtexparser.parse_file(str(library_path))
    except Exception as exc:  # pragma: no cover - parser raises custom errors
        raise ValueError(f"Failed to parse {library_path}: {exc}") from exc

    removed: list[str] = []

    for entry in library.entries:
        fields = entry.fields_dict
        url_field = fields.get("url")

        if url_field is None:
            continue

        url_value = str(url_field.value).strip()
        reason = _redundant_url_reason(entry, url_value)

        if reason is None:
            continue

        logger.info(
            "Removing redundant URL for entry %s: %s (%s)",
            entry.key,
            url_value,
            reason,
        )
        removed.append(entry.key)
        if not dry_run:
            _remove_field(entry, "url")

    if not dry_run and removed:
        logger.debug("Writing trivial-URL removal changes back to disk: %s", library_path)
        bibtex_string = bibtexparser.write_string(library)
        with open(library_path, "w", encoding="utf-8") as bib_file:
            bib_file.write(str(bibtex_string))

    return UrlNormalizationReport(removed=removed)


def extract_arxiv_identifier_from_url(url: str) -> str | None:
    """Return the arXiv ID encoded by a canonical abstract or PDF URL."""
    try:
        parsed_url = urlsplit(url.strip())
        hostname = parsed_url.hostname
    except ValueError:
        return None

    if (
        parsed_url.scheme.casefold() not in {"http", "https"}
        or hostname is None
        or hostname.casefold() not in _ARXIV_URL_HOSTS
    ):
        return None

    route, separator, identifier = parsed_url.path.lstrip("/").partition("/")
    if not separator or route.casefold() not in {"abs", "pdf"}:
        return None

    identifier = identifier.rstrip("/")
    if route.casefold() == "pdf" and identifier.casefold().endswith(".pdf"):
        identifier = identifier[:-4]

    return identifier or None


def arxiv_identifiers_match(first: str | None, second: str | None) -> bool:
    """Return whether two non-empty arXiv identifiers match case-insensitively."""
    return first is not None and second is not None and first.casefold() == second.casefold()


def _redundant_url_reason(entry: bibtexparser.model.Entry, url: str) -> str | None:
    fields = entry.fields_dict
    doi_field = fields.get("doi")
    if doi_field is not None:
        doi_value = str(doi_field.value).strip()
        if doi_value and _is_trivial_doi_url(url, doi_value):
            return f"doi={doi_value}"

    eprint_field = fields.get("eprint")
    eprinttype_field = fields.get("eprinttype")
    if eprinttype_field is None:
        eprinttype_field = fields.get("archiveprefix")
    if eprint_field is None or eprinttype_field is None:
        return None
    if str(eprinttype_field.value).strip().casefold() != "arxiv":
        return None

    eprint_value = str(eprint_field.value).strip()
    url_identifier = extract_arxiv_identifier_from_url(url)
    if arxiv_identifiers_match(url_identifier, eprint_value):
        return f"arXiv eprint={eprint_value}"

    return None


def _is_trivial_doi_url(url: str, doi: str) -> bool:
    """Check whether *url* is just a DOI resolver link for *doi*."""
    for prefix in _DOI_URL_PREFIXES:
        candidate = prefix + doi
        if url == candidate or url == candidate + "/":
            return True
    return False


def _remove_field(entry: bibtexparser.model.Entry, field_name: str) -> None:
    field_obj = entry.fields_dict.get(field_name)
    if field_obj is None:
        return
    for index, field in enumerate(entry.fields):
        if field is field_obj:
            entry.fields.pop(index)
            break

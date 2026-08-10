"""Normalization helpers for redundant identifier URL fields."""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlsplit

import bibtexparser

from biblio.bibliography import Bibliography
from biblio.results import ChangeSet, FieldDelta

_DOI_URL_PREFIXES = (
    "https://doi.org/",
    "http://doi.org/",
    "https://dx.doi.org/",
    "http://dx.doi.org/",
)
_ARXIV_URL_HOSTS = {"arxiv.org", "www.arxiv.org"}


@dataclass(frozen=True, slots=True)
class UrlNormalizationReport:
    """Summary of trivial URL removal."""

    removed: tuple[str, ...] = ()
    changes: ChangeSet = field(default_factory=ChangeSet)


def normalize_trivial_urls(bibliography: Bibliography) -> UrlNormalizationReport:
    """Remove in-memory URL fields duplicating an explicit DOI or arXiv eprint.

    A URL is redundant when it matches ``https://doi.org/{doi}`` (or an
    ``http`` / ``dx.doi.org`` variant), or when a canonical arXiv abstract or
    PDF URL contains the same identifier as an explicit arXiv ``eprint``.
    BibLaTeX can construct links from those identifier fields, so retaining
    the URL adds no information.

    """
    removed: list[str] = []
    deltas: list[FieldDelta] = []

    for entry in bibliography:
        fields = entry.fields_dict
        url_field = fields.get("url")

        if url_field is None:
            continue

        url_value = str(url_field.value).strip()
        reason = _redundant_url_reason(entry, url_value)

        if reason is None:
            continue

        removed.append(entry.key)
        deltas.append(FieldDelta(entry.key, "url", str(url_field.value), None))
        _remove_field(entry, "url")

    changes = ChangeSet(tuple(removed), tuple(deltas))
    return UrlNormalizationReport(tuple(removed), changes)


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
    for index, entry_field in enumerate(entry.fields):
        if entry_field is field_obj:
            entry.fields.pop(index)
            break

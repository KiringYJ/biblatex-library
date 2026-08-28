"""Normalization helpers for redundant DOI and exactly matched arXiv URLs."""

import unicodedata
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from biblio.bibliography import Bibliography
from biblio.identifiers import legacy_doi_comparison_token
from biblio.results import ChangeSet, FieldDelta

from .doi import matches_arxiv_doi
from .eprint import explicit_arxiv_eprint

_ARXIV_ABSTRACT_PREFIXES = (
    "https://arxiv.org/abs/",
    "http://arxiv.org/abs/",
    "https://www.arxiv.org/abs/",
    "http://www.arxiv.org/abs/",
)


@dataclass(frozen=True, slots=True)
class UrlNormalizationReport:
    """Summary of trivial URL removal."""

    removed: tuple[str, ...] = ()
    changes: ChangeSet = field(default_factory=ChangeSet)


def normalize_trivial_urls(bibliography: Bibliography) -> UrlNormalizationReport:
    """Remove equivalent bare DOI resolver or exact typed arXiv abstract links.

    DOI comparison uses its defined ASCII case equivalence, without rewriting
    stored identifiers. Keep extra URL components and exact arXiv versions.
    """
    removed: list[str] = []
    deltas: list[FieldDelta] = []

    for entry in bibliography:
        fields = {item.key.casefold(): item for item in entry.fields}
        url_field = fields.get("url")
        if url_field is None:
            continue
        url = str(url_field.value)
        doi = fields.get("doi")
        redundant = doi is not None and matches_doi_url(url, str(doi.value))
        eprint = explicit_arxiv_eprint(entry)
        if not redundant and eprint is not None:
            redundant = matches_arxiv_url(url, eprint)
        if redundant:
            entry.fields.remove(url_field)
            removed.append(entry.key)
            deltas.append(FieldDelta(entry.key, "url", url, None))

    return UrlNormalizationReport(tuple(removed), ChangeSet(tuple(removed), tuple(deltas)))


def matches_doi_url(url: str, identifier: str) -> bool:
    """Match a bare approved DOI resolver URL without losing URL components."""
    # The comparison helper intentionally discards resolver components; a
    # cleanup operation must first establish that there are none to lose.
    if not identifier or any(
        character.isspace() or unicodedata.category(character) == "Cc" or character in "?#"
        for value in (url, identifier)
        for character in value
    ):
        return False
    try:
        if urlsplit(url).scheme not in {"http", "https"}:
            return False
        return legacy_doi_comparison_token(url) == legacy_doi_comparison_token(identifier)
    except ValueError:
        return False


def matches_arxiv_url(url: str, identifier: str) -> bool:
    """Match an exact abstract URL or a bare resolver URL for the derived DOI."""
    if _matches_identifier_url(url, identifier, _ARXIV_ABSTRACT_PREFIXES):
        return True
    try:
        return urlsplit(url).scheme in {"http", "https"} and matches_arxiv_doi(url, identifier)
    except ValueError:
        return False


def _matches_identifier_url(url: str, identifier: str, prefixes: tuple[str, ...]) -> bool:
    if not identifier or any(character.isspace() or character in "?#" for character in identifier):
        return False
    return any(url == prefix + identifier for prefix in prefixes)

"""Normalization helpers for exactly regenerable identifier URL fields."""

from dataclasses import dataclass, field

from biblio.bibliography import Bibliography
from biblio.results import ChangeSet, FieldDelta

_DOI_URL_PREFIXES = (
    "https://doi.org/",
    "http://doi.org/",
    "https://dx.doi.org/",
    "http://dx.doi.org/",
)
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
    """Remove exact DOI resolver or explicitly typed arXiv abstract links.

    Keep PDF selection and every unmatched URL component, spelling, or version.
    Matching uses the exact identifier value, not identifier equivalence.
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
        redundant = doi is not None and _matches_identifier_url(
            url, str(doi.value), _DOI_URL_PREFIXES
        )
        eprint = fields.get("eprint")
        types = [
            str(fields[name].value).casefold()
            for name in ("eprinttype", "archiveprefix")
            if name in fields
        ]
        if (
            not redundant
            and eprint is not None
            and types
            and all(value == "arxiv" for value in types)
        ):
            redundant = _matches_identifier_url(url, str(eprint.value), _ARXIV_ABSTRACT_PREFIXES)
        if redundant:
            entry.fields.remove(url_field)
            removed.append(entry.key)
            deltas.append(FieldDelta(entry.key, "url", url, None))

    return UrlNormalizationReport(tuple(removed), ChangeSet(tuple(removed), tuple(deltas)))


def _matches_identifier_url(url: str, identifier: str, prefixes: tuple[str, ...]) -> bool:
    if not identifier or any(character.isspace() or character in "?#" for character in identifier):
        return False
    return any(url == prefix + identifier for prefix in prefixes)

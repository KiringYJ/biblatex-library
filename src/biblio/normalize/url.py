"""Normalization helper to remove trivial URL fields derived from DOI."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import bibtexparser
from bibtexparser.library import Library

logger = logging.getLogger(__name__)

_DOI_URL_PREFIXES = (
    "https://doi.org/",
    "http://doi.org/",
    "https://dx.doi.org/",
    "http://dx.doi.org/",
)


@dataclass(slots=True)
class UrlNormalizationReport:
    """Summary of trivial URL removal."""

    removed: list[str]


def normalize_trivial_urls(library_path: Path, *, dry_run: bool = False) -> UrlNormalizationReport:
    """Remove URL fields that are trivially derived from the DOI.

    A URL is considered trivial when it matches ``https://doi.org/{doi}``
    (or the ``http`` / ``dx.doi.org`` variants).  Biblatex can reconstruct
    such URLs automatically from the ``doi`` field, so keeping them adds
    noise without information.

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
        doi_field = fields.get("doi")

        if url_field is None or doi_field is None:
            continue

        url_value = str(url_field.value).strip()
        doi_value = str(doi_field.value).strip()

        if not doi_value:
            continue

        if _is_trivial_doi_url(url_value, doi_value):
            logger.info(
                "Removing trivial URL for entry %s: %s (doi=%s)",
                entry.key,
                url_value,
                doi_value,
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

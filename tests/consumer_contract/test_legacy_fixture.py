"""Executable documentation of the synthetic legacy migration edge cases."""

import json
from pathlib import Path
from typing import cast

import bibtexparser

from .audit import LegacyIdentifierRecord

FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "legacy-workspace"


def _identifiers() -> dict[str, LegacyIdentifierRecord]:
    data = json.loads((FIXTURE_ROOT / "identifier_collection.json").read_text(encoding="utf-8"))
    return cast(dict[str, LegacyIdentifierRecord], data)


def _bib_fields(key: str) -> dict[str, str]:
    library = bibtexparser.parse_file(str(FIXTURE_ROOT / "library.bib"))
    entry = next(entry for entry in library.entries if entry.key == key)
    return {name: str(field.value) for name, field in entry.fields_dict.items()}


def test_fixture_distinguishes_arxiv_derived_doi_from_publisher_doi() -> None:
    """Fixture carries both derived-arXiv and distinct publisher DOI cases."""
    identifiers = _identifiers()

    assert identifiers["preprint-2024-42407503"]["identifiers"]["doi"] == (
        "10.48550/arXiv.2401.01234"
    )
    assert identifiers["publisher-2024-052397b0"]["identifiers"]["doi"] == ("10.5555/publisher.1")


def test_fixture_contains_formatting_only_isbn_difference() -> None:
    """Fixture contrasts exact legacy ISBN digits with formatted BibLaTeX."""
    legacy_isbn = _identifiers()["isbn-2020-b4e25867"]["identifiers"]["isbn13"]
    bib_isbn = _bib_fields("isbn-2020-b4e25867")["isbn"]

    assert legacy_isbn == "9780306406157"
    assert bib_isbn == "978-0-306-40615-7"


def test_fixture_contains_semantic_url_conflict() -> None:
    """Fixture has distinct legacy and BibLaTeX URLs that require resolution."""
    legacy_url = _identifiers()["website-2023-82a77c54"]["identifiers"]["url"]
    bib_url = _bib_fields("website-2023-82a77c54")["url"]

    assert legacy_url != bib_url


def test_fixture_contains_acm_direct_field_url_conflict() -> None:
    """Fixture has a direct ACM DOI that disagrees with its ACM URL candidate."""
    fields = _bib_fields("acm-1994-47a86cde")

    assert fields["acmdl_doi"] not in fields["url"]


def test_fixture_contains_missing_handle_case() -> None:
    """Fixture requires adding a legacy handle absent from BibLaTeX."""
    legacy_handle = _identifiers()["repository-2022-8c60c41b"]["identifiers"]["hdl"]
    fields = _bib_fields("repository-2022-8c60c41b")

    assert legacy_handle == "20.500.12345/CaseSensitive"
    assert "hdl" not in fields

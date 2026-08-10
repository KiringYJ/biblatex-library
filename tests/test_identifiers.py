"""Tests for pure identifier identity helpers."""

import hashlib

import pytest

from biblio.identifiers import (
    CanonicalDoi,
    canonicalize_new_doi,
    hash_canonical_new_doi,
    hash_exact_legacy_identifier,
    is_derived_arxiv_doi,
    isbn13_digits_from_isbn10,
    isbn_comparison_token,
    legacy_doi_comparison_token,
)


def test_valid_isbn10_and_isbn13_share_one_canonical_comparison_token() -> None:
    assert isbn13_digits_from_isbn10("0-387-97926-3") == "9780387979267"
    assert isbn_comparison_token("0-387-97926-3") == "9780387979267"
    assert isbn_comparison_token("978-0-387-97926-7") == "9780387979267"


def test_invalid_isbn_keeps_formatting_only_legacy_comparison() -> None:
    assert isbn_comparison_token(" ABC-123 ") == "ABC123"


@pytest.mark.parametrize(
    "raw",
    [
        "10.1000/ABC",
        " 10.1000/ABC ",
        "DOI:10.1000/ABC",
        " DOI:  10.1000/ABC  ",
        "https://doi.org/10.1000%2FABC",
        "http://www.doi.org/10.1000/ABC",
        "HTTP://DX.DOI.ORG/10.1000/ABC",
    ],
)
def test_equivalent_new_doi_inputs_have_one_value_and_hash(raw: str) -> None:
    canonical = canonicalize_new_doi(raw)

    assert canonical.value == "10.1000/abc"
    assert hash_canonical_new_doi(canonical) == hashlib.sha256(b"10.1000/abc").hexdigest()[:8]


def test_resolver_query_and_fragment_are_stripped_and_flagged() -> None:
    canonical = canonicalize_new_doi("https://doi.org/10.1000/ABC?source=x#page")

    assert canonical == CanonicalDoi(
        value="10.1000/abc",
        had_query=True,
        had_fragment=True,
    )


def test_bare_doi_query_and_fragment_characters_are_not_uri_components() -> None:
    canonical = canonicalize_new_doi("10.1000/ABC?source=x#page")

    assert canonical.value == "10.1000/abc?source=x#page"
    assert not canonical.had_query
    assert not canonical.had_fragment


def test_resolver_path_is_percent_decoded_once_with_strict_utf8() -> None:
    assert canonicalize_new_doi("https://doi.org/10.1000%2Fcaf%C3%A9").value == ("10.1000/café")

    with pytest.raises(ValueError, match="first slash"):
        canonicalize_new_doi("https://doi.org/10.1000%252FABC")
    with pytest.raises(ValueError, match="valid UTF-8"):
        canonicalize_new_doi("https://doi.org/10.1000%2F%FF")
    with pytest.raises(ValueError, match="invalid percent escape"):
        canonicalize_new_doi("https://doi.org/10.1000%2GABC")


def test_new_doi_canonicalization_preserves_unicode_without_normalization() -> None:
    composed = canonicalize_new_doi("10.1000/CAFÉ")
    decomposed = canonicalize_new_doi("10.1000/CAFE\u0301")

    assert composed.value == "10.1000/cafÉ"
    assert decomposed.value == "10.1000/cafe\u0301"
    assert composed.value != decomposed.value


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("", "must not be empty"),
        ("doi:https://doi.org/10.1000/ABC", "must start with '10.'"),
        ("doi:   ", "must not be empty"),
        ("doi:10.1000/ABC?source=x", "query or fragment"),
        ("doi:10.1000/ABC#page", "query or fragment"),
        ("ftp://doi.org/10.1000/ABC", "HTTP or HTTPS"),
        ("https://user@doi.org/10.1000/ABC", "userinfo or a port"),
        ("https://doi.org:443/10.1000/ABC", "userinfo or a port"),
        ("https://example.org/10.1000/ABC", "approved DOI resolver"),
        ("https://prefix.doi.org/10.1000/ABC", "approved DOI resolver"),
        ("11.1000/ABC", "must start with '10.'"),
        ("10./ABC", "registrant segment"),
        ("10.1000", "first slash"),
        ("10.1000/", "nonempty suffix"),
        ("10.1000/AB\u0000C", "control characters"),
    ],
)
def test_invalid_new_doi_inputs_are_rejected(raw: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        canonicalize_new_doi(raw)


def test_historical_hash_and_legacy_comparison_are_deliberately_separate() -> None:
    legacy = " HTTPS://DOI.ORG/10.1000/ABC "

    assert (
        hash_exact_legacy_identifier(legacy)
        == hashlib.sha256(legacy.encode("utf-8")).hexdigest()[:8]
    )
    assert legacy_doi_comparison_token(legacy) == "10.1000/abc"
    assert hash_exact_legacy_identifier(legacy) != hash_canonical_new_doi(
        canonicalize_new_doi(legacy)
    )


@pytest.mark.parametrize(
    ("doi", "eprint", "expected"),
    [
        ("10.48550/arxiv.2606.10830", "2606.10830", True),
        ("10.48550/ARXIV.2606.10830V2", "arXiv:2606.10830v2", True),
        ("10.48550/arxiv.2606.10830v2", "2606.10830v1", False),
        ("10.1000/published.2606", "2606.10830", False),
        ("10.48550/arxiv.2606.10830", "", False),
    ],
)
def test_derived_arxiv_doi_classification(doi: str, eprint: str, expected: bool) -> None:
    assert is_derived_arxiv_doi(doi, eprint) is expected

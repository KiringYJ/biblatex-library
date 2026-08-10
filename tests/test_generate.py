"""Tests for pure citekey name and year extraction."""

import pytest

from biblio.generate import citekey_stem, extract_lastname, extract_year


@pytest.mark.parametrize(
    ("author", "sortname", "expected"),
    [
        ("Bredon, Glen E.", "", "bredon"),
        ("Glen E. Bredon", "", "bredon"),
        ("Bredon, Glen E. and Smith, John", "", "bredon"),
        ("{The LMFDB Collaboration}", "LMFDB Collaboration", "lmfdb"),
        ("{LMFDB Collaboration}", "", "lmfdb"),
        ("Müller, Hans", "", "muller"),
        ("", "", "unknown"),
        ("   ", "", "unknown"),
    ],
)
def test_extract_lastname(author: str, sortname: str, expected: str) -> None:
    assert extract_lastname(author, sortname) == expected


@pytest.mark.parametrize(
    ("date", "expected"),
    [
        ("1993", "1993"),
        ("1993-05-15", "1993"),
        ("1993/1994", "1993"),
        ("circa 1993", "circa 1993"),
        ("3000", "3000"),
        ("abc", "abc"),
        ("", "unknown"),
    ],
)
def test_extract_year(date: str, expected: str) -> None:
    assert extract_year(date) == expected


def test_citekey_stem_centralizes_shorthand_editor_and_date_fallbacks() -> None:
    assert citekey_stem(
        shorthand="ÉGA IV",
        editor="Ignored, Editor",
        year="1964",
    ) == ("egaiv", "1964")
    assert citekey_stem(
        editor="Editor, Erin",
        sortname="Sorting Name",
        date="2021-05",
    ) == ("editor", "2021")


def test_citekey_stem_preserves_present_but_empty_field_semantics() -> None:
    assert citekey_stem(author="", editor="Editor, Erin", date="", year="2021") == (
        "unknown",
        "unknown",
    )

"""Tests for pure publisher/location normalization."""

import bibtexparser

from biblio.bibliography import Bibliography, IdentityIndex
from biblio.normalize.publisher import normalize_publisher_location


def _bibliography(source: str) -> Bibliography:
    library = bibtexparser.parse_string(source)
    return Bibliography(library.blocks, IdentityIndex(library.entries))


def test_splits_unambiguous_publisher_location() -> None:
    bibliography = _bibliography("@book{one, publisher={Springer, Berlin}}\n")

    report = normalize_publisher_location(bibliography)

    assert report.flagged == ("one",)
    assert report.fixed == ("one",)
    assert report.changes.changed
    assert bibliography.resolve("one").fields_dict["publisher"].value == "Springer"
    assert bibliography.resolve("one").fields_dict["location"].value == "Berlin"


def test_flags_ambiguous_values_but_does_not_change_them() -> None:
    bibliography = _bibliography(
        "@book{multi, publisher={Press, City, Country}}\n"
        "@book{suffix, publisher={Press, Inc.}}\n"
        "@article{article, publisher={Press, City}}\n"
    )

    report = normalize_publisher_location(bibliography)

    assert report.flagged == ("multi", "suffix")
    assert report.fixed == ()
    assert report.changes.changed is False
    assert bibliography.resolve("suffix").fields_dict["publisher"].value == "Press, Inc."

"""Tests for whole-book page-extent normalization."""

import bibtexparser

from biblio.bibliography import Bibliography, IdentityIndex
from biblio.normalize.pagination import normalize_book_pagination


def _bibliography(source: str) -> Bibliography:
    library = bibtexparser.parse_string(source)
    return Bibliography(library.blocks, IdentityIndex(library.entries))


def test_book_pages_are_renamed_to_pagetotal() -> None:
    bibliography = _bibliography("@book{one,pages={xiv+557}}\n")

    report = normalize_book_pagination(bibliography)

    fields = bibliography.resolve("one").fields_dict
    assert report.conflicts == ()
    assert report.changes.changed_keys == ("one",)
    assert "pages" not in fields
    assert fields["pagetotal"].value == "xiv+557"


def test_equal_pagetotal_removes_redundant_pages() -> None:
    bibliography = _bibliography("@book{one,pages={228},pagetotal={228}}\n")

    report = normalize_book_pagination(bibliography)

    fields = bibliography.resolve("one").fields_dict
    assert report.changes.changed
    assert "pages" not in fields
    assert fields["pagetotal"].value == "228"


def test_conflicting_pagetotal_is_not_overwritten() -> None:
    bibliography = _bibliography("@book{one,pages={100},pagetotal={200}}\n")

    report = normalize_book_pagination(bibliography)

    assert report.changes.changed is False
    assert report.conflicts == ("one",)
    assert report.ambiguous == ()
    assert bibliography.resolve("one").fields_dict["pages"].value == "100"


def test_book_page_range_is_left_for_manual_review() -> None:
    bibliography = _bibliography("@book{one,pages={10--20}}\n")

    report = normalize_book_pagination(bibliography)

    assert report.changes.changed is False
    assert report.ambiguous == ("one",)
    assert "pages" in bibliography.resolve("one").fields_dict


def test_conflicting_range_and_pagetotal_is_reported_as_conflict() -> None:
    bibliography = _bibliography("@book{one,pages={10--20},pagetotal={200}}\n")

    report = normalize_book_pagination(bibliography)

    assert report.conflicts == ("one",)
    assert report.ambiguous == ()


def test_contained_work_pages_are_not_totaled() -> None:
    bibliography = _bibliography("@incollection{one,pages={10--20}}\n")

    assert normalize_book_pagination(bibliography).changes.changed is False
    assert "pages" in bibliography.resolve("one").fields_dict

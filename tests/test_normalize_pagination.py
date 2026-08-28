"""MR metadata, extent syntax, and scope gates for whole-book pagination."""

import bibtexparser
import pytest

from biblio.bibliography import Bibliography, IdentityIndex
from biblio.normalize.pagination import normalize_book_pagination


def _bibliography(source: str) -> Bibliography:
    library = bibtexparser.parse_string(source)
    assert not library.failed_blocks
    return Bibliography(library.blocks, IdentityIndex(library.entries))


def _snapshot(bibliography: Bibliography) -> tuple[tuple[tuple[str, str], ...], ...]:
    return tuple(
        tuple((field.key, str(field.value)) for field in entry.fields) for entry in bibliography
    )


@pytest.mark.parametrize("marker", ["mrnumber", "MRCLASS", "MrReviewer"])
@pytest.mark.parametrize("extent", ["123", "xiv+557", " XIV + 557 "])
def test_mr_book_extent_migrates_without_rewriting_values(marker: str, extent: str) -> None:
    bibliography = _bibliography(
        f"@book{{one,title={{Book}},PAGES={{{extent}}},{marker}={{marker-value}}}}"
    )

    report = normalize_book_pagination(bibliography)

    assert not report.conflicts and not report.ambiguous
    assert report.changes.changed_keys == ("one",)
    assert _snapshot(bibliography) == (
        (("title", "Book"), ("pagetotal", extent), (marker, "marker-value")),
    )
    assert [(delta.field, delta.before, delta.after) for delta in report.changes.field_deltas] == [
        ("pages", extent, None),
        ("pagetotal", None, extent),
    ]
    assert not normalize_book_pagination(bibliography).changes.changed


@pytest.mark.parametrize(
    "fields",
    [
        "pages={123}",
        "pages={123},mrnumber={}",
        "pages={123},mrclass={ },mrreviewer={}",
        "pages={123},mri={123}",
        "pages={123},url={https://mathscinet.ams.org/mathscinet/}",
        "pages={123},journal={J. Tests},fjournal={Journal of Tests}",
        "pages={123},mrnumber={MR123},chapter={3}",
        "pages={123},mrnumber={MR123},CHAPTER={}",
        "pages={123},mrnumber={MR123},pagination={verse}",
        "pages={123},mrnumber={MR123},bookpagination={line}",
        "pages={123},mrnumber={MR123},pagination={}",
        "pages={10--20},mrnumber={MR123}",
        "pages={0},mrnumber={MR123}",
        "pages={-3},mrnumber={MR123}",
        "pages={123 pp.},mrnumber={MR123}",
        "pages={xiii, 123},mrnumber={MR123}",
        "pages={IC+123},mrnumber={MR123}",
        "pages={xivx+123},mrnumber={MR123}",
        "pages={+123},mrnumber={MR123}",
        "pages={１２３},mrnumber={MR123}",
    ],
)
def test_unverified_or_scoped_values_are_unchanged(fields: str) -> None:
    bibliography = _bibliography(f"@book{{one,{fields}}}")
    before = _snapshot(bibliography)

    report = normalize_book_pagination(bibliography)

    assert _snapshot(bibliography) == before
    assert not report.changes.changed
    assert report.ambiguous == ("one",)


@pytest.mark.parametrize("entry_type", ["article", "inbook", "incollection", "inproceedings"])
def test_contained_work_pages_are_never_totaled(entry_type: str) -> None:
    bibliography = _bibliography(f"@{entry_type}{{one,pages={{123}},mrnumber={{MR123}}}}")
    before = _snapshot(bibliography)

    report = normalize_book_pagination(bibliography)

    assert not report.changes.changed
    assert not report.ambiguous and not report.conflicts
    assert _snapshot(bibliography) == before


@pytest.mark.parametrize("total", ["456", "", " 123 "])
def test_conflicting_total_is_never_overwritten(total: str) -> None:
    bibliography = _bibliography(
        f"@book{{one,pages={{123}},pagetotal={{{total}}},mrnumber={{MR1}}}}"
    )
    before = _snapshot(bibliography)

    report = normalize_book_pagination(bibliography)

    assert report.conflicts == ("one",)
    assert not report.changes.changed
    assert _snapshot(bibliography) == before


def test_equal_existing_total_deduplicates_only_a_verified_mr_extent() -> None:
    bibliography = _bibliography(
        "@book{mr,pages={123},PAGETOTAL={123},mrnumber={MR1}}"
        "@book{other,pages={123},pagetotal={123}}"
    )

    report = normalize_book_pagination(bibliography)

    assert report.changes.changed_keys == ("mr",)
    assert bibliography.resolve("mr").fields_dict["PAGETOTAL"].value == "123"
    assert "pages" not in bibliography.resolve("mr").fields_dict
    assert bibliography.resolve("other").fields_dict["pages"].value == "123"


def test_explicit_page_unit_is_compatible_with_mr_extent() -> None:
    bibliography = _bibliography("@book{one,pages={123},pagination={page},mrclass={53C}}")
    assert normalize_book_pagination(bibliography).changes.changed_keys == ("one",)
    assert bibliography.resolve("one").fields_dict["pagination"].value == "page"


@pytest.mark.parametrize("duplicate", ["pages", "pagetotal", "mrnumber", "chapter", "pagination"])
def test_duplicate_field_preflight_precedes_all_pagination_mutation(duplicate: str) -> None:
    bibliography = _bibliography(
        "@book{first,pages={123},mrnumber={MR1}}"
        f"@book{{second,{duplicate}={{One}},{duplicate.upper()}={{Two}}}}"
    )
    before = _snapshot(bibliography)
    with pytest.raises(ValueError, match=f"duplicate '{duplicate}' fields"):
        normalize_book_pagination(bibliography)
    assert _snapshot(bibliography) == before

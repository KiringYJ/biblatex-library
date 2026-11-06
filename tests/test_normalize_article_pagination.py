"""Bounded MR article identifiers and atomic structured-pagination migration."""

import bibtexparser
import pytest

from biblio.bibliography import Bibliography, IdentityIndex
from biblio.normalize.article_pagination import (
    is_article_pagination_candidate,
    is_mr_article_pagination,
    normalize_article_pagination,
    parse_article_pagination,
)


def _bibliography(source: str) -> Bibliography:
    library = bibtexparser.parse_string(source)
    assert not library.failed_blocks
    return Bibliography(library.blocks, IdentityIndex(library.entries))


def _snapshot(bibliography: Bibliography) -> tuple[tuple[tuple[str, str], ...], ...]:
    return tuple(
        tuple((field.key, str(field.value)) for field in entry.fields) for entry in bibliography
    )


@pytest.mark.parametrize("label", ["Paper No.", "Paper", "Art. ID", "Art.", "pApEr nO."])
@pytest.mark.parametrize("identifier", ["072", "e7", "3.26", "rnm075", "E007.02"])
@pytest.mark.parametrize("suffix,total", [("", None), (", 18", "18"), (", 18 pp.", "18")])
def test_parse_preserves_exact_identifier(
    label: str, identifier: str, suffix: str, total: str | None
) -> None:
    result = parse_article_pagination(f"  {label} {identifier}{suffix}  ")
    assert result is not None
    assert (result.eid, result.pagetotal) == (identifier, total)


def test_parser_accepts_flexible_whitespace() -> None:
    result = parse_article_pagination("\tPaper\nNo. \tE007.02 ,\n18\tpp. ")
    assert result is not None and (result.eid, result.pagetotal) == ("E007.02", "18")


@pytest.mark.parametrize(
    "value",
    [
        "066001, 18",
        "Paper No. 7, xiv+18",
        "Art. e7, iv, 18",
        "Paper No. 7, 0",
        "Paper No. 7, 018",
        "Paper No. 7, １２",
        "Paper No. ７, 18",
        "Paper No. alpha",
        "Paper No. 7 pp.",
        "Paper No. 7, 18 pp",
        "Paper No. 7, 18 pages",
        "Paper No. 3.26.1a",
        "Paper No. 7--9, 18",
        "Paper No. 7, 18, 19",
        "Art.ID 7, 18",
        "paperwork 7, 18",
        "Article 7, 18",
        "3--45, 240",
        "123",
        "",
    ],
)
def test_parser_preserves_unsupported_values(value: str) -> None:
    assert parse_article_pagination(value) is None


@pytest.mark.parametrize(
    "value",
    [
        "Paper No. 7",
        "Art. alpha",
        "Paper No. 7, xiv+18",
        "066001, 18",
        "e7, iv+18",
        "045, front matter+26",
        "019, front matter + 52",
        "129, i, 152",
    ],
)
def test_candidate_recognizes_reviewable_attempts(value: str) -> None:
    assert is_article_pagination_candidate(value)


@pytest.mark.parametrize(
    "value", ["3--45, 240", "20--34, electronic", "1--18", "1, 3, 7", "123", "18 pp.", ""]
)
def test_candidate_excludes_ordinary_pages(value: str) -> None:
    assert not is_article_pagination_candidate(value)


@pytest.mark.parametrize("marker", ["mrnumber", "MRCLASS", "MrReviewer"])
def test_migration_preserves_keys_order_position_and_exact_deltas(marker: str) -> None:
    bibliography = _bibliography(
        f"@ARTICLE{{one,title={{T}},PAGES={{Paper No. 072, 18 pp.}},{marker}={{M}}}}"
        "@article{two,pages={Art. e7},mrnumber={M}}"
    )
    report = normalize_article_pagination(bibliography)
    assert not report.conflicts and not report.ambiguous
    assert report.changes.changed_keys == ("one", "two")
    assert _snapshot(bibliography) == (
        (("title", "T"), ("eid", "072"), ("pagetotal", "18"), (marker, "M")),
        (("eid", "e7"), ("mrnumber", "M")),
    )
    assert [(d.canonical_key, d.field, d.before, d.after) for d in report.changes.field_deltas] == [
        ("one", "pages", "Paper No. 072, 18 pp.", None),
        ("one", "eid", None, "072"),
        ("one", "pagetotal", None, "18"),
        ("two", "pages", "Art. e7", None),
        ("two", "eid", None, "e7"),
    ]
    assert tuple(entry.key for entry in bibliography) == ("one", "two")
    assert report.changes.order_delta is None and not report.changes.alias_deltas
    second = normalize_article_pagination(bibliography)
    assert not second.changes.changed and not second.conflicts and not second.ambiguous


@pytest.mark.parametrize(
    "targets",
    ["eid={different}", "eid={}", "pagetotal={19}", "pagetotal={}", "eid={072},pagetotal={ 18 }"],
)
def test_target_conflicts_preserve_whole_entry_atomically(targets: str) -> None:
    bibliography = _bibliography(
        f"@article{{one,pages={{Paper No. 072, 18}},{targets},mrnumber={{M}}}}"
    )
    before = _snapshot(bibliography)
    report = normalize_article_pagination(bibliography)
    assert report.conflicts == ("one",) and not report.ambiguous
    assert not report.changes.changed and _snapshot(bibliography) == before


@pytest.mark.parametrize(
    "targets,expected",
    [
        ("EID={072},PAGETOTAL={18}", (("EID", "072"), ("PAGETOTAL", "18"))),
        ("EID={072}", (("pagetotal", "18"), ("EID", "072"))),
        ("PAGETOTAL={18}", (("eid", "072"), ("PAGETOTAL", "18"))),
    ],
)
def test_equal_targets_retain_original_fields_and_only_add_missing_targets(
    targets: str, expected: tuple[tuple[str, str], ...]
) -> None:
    bibliography = _bibliography(
        f"@article{{one,pages={{Paper No. 072, 18}},{targets},mrnumber={{M}}}}"
    )
    report = normalize_article_pagination(bibliography)
    assert report.changes.changed_keys == ("one",)
    assert _snapshot(bibliography)[0] == (*expected, ("mrnumber", "M"))
    assert all(d.before is None for d in report.changes.field_deltas[1:])


def test_identifier_only_retains_unrelated_existing_total() -> None:
    bibliography = _bibliography("@article{one,pages={Art. e7},pagetotal={other},mrnumber={M}}")
    assert normalize_article_pagination(bibliography).changes.changed_keys == ("one",)
    assert _snapshot(bibliography)[0] == (("eid", "e7"), ("pagetotal", "other"), ("mrnumber", "M"))


@pytest.mark.parametrize(
    "fields",
    [
        "",
        "mrnumber={}",
        "mrclass={ },mrreviewer={}",
        "mri={M}",
        "url={https://mathscinet.ams.org/}",
        "mrnumber={M},chapter={}",
        "mrnumber={M},pagination={verse}",
        "mrnumber={M},bookpagination={line}",
        "mrnumber={M},pagination={}",
        "mrnumber={M},pagination={Page}",
    ],
)
def test_scope_failures_are_review_only(fields: str) -> None:
    bibliography = _bibliography(f"@article{{one,pages={{Paper No. 7}},title={{T}},{fields}}}")
    before = _snapshot(bibliography)
    assert not is_mr_article_pagination(bibliography.resolve("one"))
    report = normalize_article_pagination(bibliography)
    assert report.ambiguous == ("one",) and not report.conflicts
    assert not report.changes.changed and _snapshot(bibliography) == before


def test_scope_predicate_ignores_targets_and_allows_exact_page_units() -> None:
    bibliography = _bibliography(
        "@article{one,pages={Art. 3.26},pagination={page},"
        "bookpagination={page},mrclass={M},eid={different}}"
    )
    assert is_mr_article_pagination(bibliography.resolve("one"))


@pytest.mark.parametrize("entry_type", ["book", "inbook", "incollection", "inproceedings"])
def test_nonarticle_entries_are_untouched_without_diagnostics(entry_type: str) -> None:
    bibliography = _bibliography(f"@{entry_type}{{one,pages={{Paper No. 7}},mrnumber={{M}}}}")
    before = _snapshot(bibliography)
    report = normalize_article_pagination(bibliography)
    assert not report.changes.changed and not report.ambiguous and not report.conflicts
    assert _snapshot(bibliography) == before


def test_range_with_existing_eid_is_untouched_without_diagnostics() -> None:
    bibliography = _bibliography("@article{one,pages={3--45, 240},eid={7},mrnumber={M}}")
    before = _snapshot(bibliography)
    report = normalize_article_pagination(bibliography)
    assert not report.changes.changed and not report.ambiguous and not report.conflicts
    assert _snapshot(bibliography) == before


@pytest.mark.parametrize(
    "value",
    [
        "066001, 18",
        "Paper No. 7, xiv+18",
        "Art. alpha",
        "045, front matter+26",
        "019, front matter + 52",
        "129, i, 152",
    ],
)
def test_unsupported_candidates_remain_review_only(value: str) -> None:
    bibliography = _bibliography(f"@article{{one,pages={{{value}}},mrnumber={{M}}}}")
    before = _snapshot(bibliography)
    report = normalize_article_pagination(bibliography)
    assert report.ambiguous == ("one",) and not report.conflicts
    assert not report.changes.changed and _snapshot(bibliography) == before


@pytest.mark.parametrize(
    "duplicate",
    [
        "pages",
        "eid",
        "pagetotal",
        "mrnumber",
        "mrclass",
        "mrreviewer",
        "chapter",
        "pagination",
        "bookpagination",
    ],
)
def test_duplicate_preflight_checks_all_entries_before_any_mutation(duplicate: str) -> None:
    bibliography = _bibliography(
        "@article{first,pages={Art. 7},mrnumber={M}}"
        f"@book{{second,{duplicate}={{One}},{duplicate.upper()}={{Two}}}}"
    )
    before = _snapshot(bibliography)
    with pytest.raises(ValueError, match=f"duplicate '{duplicate}' fields"):
        normalize_article_pagination(bibliography)
    assert _snapshot(bibliography) == before

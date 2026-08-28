"""Tests for deterministic, source-free bibliography compliance findings."""

import bibtexparser
import pytest

from biblio.audit import audit_bibliography
from biblio.bibliography import Bibliography, IdentityIndex
from biblio.normalize.pipeline import normalize_bibliography


def _bibliography(source: str) -> Bibliography:
    library = bibtexparser.parse_string(source)
    return Bibliography(library.blocks, IdentityIndex(library.entries))


def test_audit_offers_only_contract_proven_fixes() -> None:
    bibliography = _bibliography(
        """\
@article{legacy,
  author = {Macrì , Emanuele},
  title = {Article},
  journal = {J. Tests},
  fjournal = {Journal of Tests},
  mrclass = {53C},
  issn = {2049-3630}
}
@book{extent,
  author = {Doe, Jane},
  title = {Book},
  pages = {xiv+557}
}
"""
    )

    result = audit_bibliography(bibliography)

    findings = {(finding.code, finding.fields): finding for finding in result.findings}
    assert not result.clean
    assert findings[("legacy-journal-field", ("journal",))].fix_action == "journal-fields"
    assert findings[("legacy-journal-field", ("fjournal",))].fix_action == "journal-fields"
    assert findings[("book-pages-review", ("pages",))].fix_action is None
    assert findings[("name-comma-spacing", ("author",))].fix_action == "name-spacing"


def test_audit_reports_deterministic_issues_that_need_a_human_choice() -> None:
    bibliography = _bibliography(
        """\
@article{serial,
  title = {Article},
  issn = {0028-0836, 1476-4687},
  eissn = {1476-4687}
}
@book{edition,
  title = {Book},
  date = {1995},
  edition = {1973}
}
"""
    )

    result = audit_bibliography(bibliography)

    findings = {finding.code: finding for finding in result.findings}
    assert findings["multiple-issn"].fix_action is None
    assert findings["nonstandard-eissn"].fix_action is None
    assert findings["year-like-edition"].fix_action is None


def test_audit_reports_invalid_single_issn() -> None:
    result = audit_bibliography(_bibliography("@article{bad,title={Article},issn={1234-5678}}\n"))

    finding = next(finding for finding in result.findings if finding.code == "invalid-issn")
    assert finding.values == ("1234-5678",)
    assert finding.fix_action is None


def test_audit_does_not_guess_whether_journal_alone_is_full_or_short() -> None:
    result = audit_bibliography(
        _bibliography("@article{one,title={Article},journal={Journal of Tests}}\n")
    )

    finding = next(finding for finding in result.findings if finding.code == "legacy-journal-field")
    assert finding.fix_action is None


def test_audit_reports_known_invalid_field_type_placements() -> None:
    bibliography = _bibliography(
        """\
@online{online,title={Notes},type={Lecture notes},pagetotal={155}}
@unpublished{draft,title={Draft},institution={University},volume={1}}
"""
    )

    result = audit_bibliography(bibliography)

    placements = [
        (finding.canonical_keys[0], finding.fields[0])
        for finding in result.findings
        if finding.code == "invalid-field-placement"
    ]
    assert placements == [
        ("online", "pagetotal"),
        ("online", "type"),
        ("draft", "institution"),
        ("draft", "volume"),
    ]


def test_audit_does_not_offer_autofix_for_conflicting_targets() -> None:
    bibliography = _bibliography(
        """\
@article{journal,
  title = {Article},
  journal = {Legacy title},
  journaltitle = {Different title}
}
@book{book,
  title = {Book},
  pages = {100},
  pagetotal = {200}
}
"""
    )

    result = audit_bibliography(bibliography)

    findings = {finding.code: finding for finding in result.findings}
    assert findings["conflicting-journal-field"].fix_action is None
    assert findings["book-pages-review"].fix_action is None


def test_audit_does_not_call_journal_and_shortjournal_a_conflict() -> None:
    result = audit_bibliography(
        _bibliography("@article{one,journal={Journal of Tests},shortjournal={J. Tests}}")
    )

    assert not any(finding.code == "conflicting-journal-field" for finding in result.findings)
    assert all(finding.fix_action is None for finding in result.findings)


def test_audit_does_not_assign_legacy_journal_values_to_title_roles() -> None:
    result = audit_bibliography(
        _bibliography(
            "@article{one,journal={First value},fjournal={First full},issn={2049-3630}}"
            "@article{two,journal={Other value},fjournal={Other full},issn={2049-3630}}"
        )
    )

    assert not any(finding.code.endswith("-variant") for finding in result.findings)


def test_mr_pair_audit_compares_the_declared_destinations() -> None:
    result = audit_bibliography(
        _bibliography(
            "@article{one,journal={J. Tests},fjournal={Journal of Tests},"
            "journaltitle={Journal of Tests},mrnumber={MR123}}"
        )
    )

    assert not any(finding.code == "conflicting-journal-field" for finding in result.findings)
    assert {finding.fix_action for finding in result.findings} == {"journal-fields"}


def test_mr_pair_conflict_never_advertises_partial_migration() -> None:
    result = audit_bibliography(
        _bibliography(
            "@article{one,journal={J. Tests},fjournal={Journal of Tests},"
            "shortjournal={Other},mrreviewer={Reviewer}}"
        )
    )

    assert any(finding.code == "conflicting-journal-field" for finding in result.findings)
    assert all(finding.fix_action is None for finding in result.findings)


def test_name_audit_does_not_offer_changes_inside_protected_or_escaped_text() -> None:
    result = audit_bibliography(
        _bibliography(r"@article{one,author={{Research , Development}},editor={Doe\ , John}}")
    )

    assert all(finding.fix_action is None for finding in result.findings)


def test_audit_does_not_treat_a_book_page_range_as_total_extent() -> None:
    result = audit_bibliography(_bibliography("@book{book,title={Book},pages={10--20}}\n"))

    finding = next(finding for finding in result.findings if finding.code == "book-pages-review")
    assert finding.fix_action is None


def test_audit_correlates_internal_variants_without_authority_lookup() -> None:
    bibliography = _bibliography(
        """\
@article{one,
  title = {One},
  journaltitle = {Compositio Mathematica},
  shortjournal = {Compos. Math.},
  issn = {0010-437X}
}
@article{two,
  title = {Two},
  journaltitle = {Compositio Mathematica},
  shortjournal = {Compositio Math.},
  issn = {0010-437X}
}
@book{series-one,title={One},series={Encyclopedia of Mathematics and Its Applications}}
@book{series-two,title={Two},series={Encyclopedia of Mathematics and its Applications}}
"""
    )

    result = audit_bibliography(bibliography)

    findings = {finding.code: finding for finding in result.findings}
    assert findings["journal-abbreviation-variant"].canonical_keys == ("one", "two")
    assert findings["journal-abbreviation-variant"].fix_action is None
    assert findings["series-case-variant"].values == (
        "Encyclopedia of Mathematics and Its Applications",
        "Encyclopedia of Mathematics and its Applications",
    )


def test_clean_audit_is_an_explicit_success() -> None:
    result = audit_bibliography(
        _bibliography(
            "@article{clean,author={Doe, Jane},title={Article},"
            "journaltitle={Journal},shortjournal={J.},issn={2049-3630}}\n"
        )
    )

    assert result.clean
    assert result.findings == ()


@pytest.mark.parametrize(
    "action, source",
    [
        ("journal-fields", "@article{x,journal={Short},fjournal={Full}}"),
        ("journal-fields", "@article{x,journal={Short},fjournal={Full},mrnumber={}}"),
        ("journal-fields", "@article{x,journal={Short},fjournal={Full},mrnumber={MR1}}"),
        ("journal-fields", "@article{x,journal={Short},fjournal={Full},MRCLASS={53C}}"),
        ("journal-fields", "@article{x,journal={Short},mrreviewer={Reviewer}}"),
        (
            "journal-fields",
            "@article{x,journal={Short},fjournal={Full},mrnumber={MR1},shortjournal={Other}}",
        ),
        ("book-pagination", "@book{x,pages={123}}"),
        ("book-pagination", "@book{x,pages={123},mrnumber={}}"),
        ("book-pagination", "@book{x,pages={123},mrnumber={MR1}}"),
        ("book-pagination", "@book{x,pages={xiv+123},MRCLASS={53C}}"),
        ("book-pagination", "@book{x,pages={10--20},mrnumber={MR1}}"),
        ("book-pagination", "@book{x,pages={123},mrnumber={MR1},chapter={3}}"),
        ("book-pagination", "@book{x,pages={123},mrnumber={MR1},pagination={verse}}"),
        ("book-pagination", "@book{x,pages={123},mrnumber={MR1},pagetotal={456}}"),
        ("book-pagination", "@article{x,pages={123},mrnumber={MR1}}"),
    ],
)
def test_audit_fix_suggestions_match_mr_normalizer_preconditions(action: str, source: str) -> None:
    result = audit_bibliography(_bibliography(source))
    preview = normalize_bibliography(_bibliography(source), action)

    assert (
        any(finding.fix_action == action for finding in result.findings) == preview.changes.changed
    )


def test_unmarked_pair_is_not_assigned_mr_title_roles() -> None:
    result = audit_bibliography(
        _bibliography("@article{x,journal={Short},fjournal={Full},shortjournal={Different}}")
    )

    assert all(finding.fix_action is None for finding in result.findings)
    assert not any(finding.code == "conflicting-journal-field" for finding in result.findings)


def test_duplicate_mr_markers_never_advertise_autofix() -> None:
    result = audit_bibliography(
        _bibliography(
            "@article{journal,journal={Short},fjournal={Full},mrnumber={},MRNUMBER={MR1}}"
            "@book{book,pages={123},mrnumber={},MRNUMBER={MR1}}"
        )
    )

    assert all(finding.fix_action is None for finding in result.findings)

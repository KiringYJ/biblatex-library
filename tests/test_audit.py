"""Tests for deterministic, source-free bibliography compliance findings."""

import bibtexparser

from biblio.audit import audit_bibliography
from biblio.bibliography import Bibliography, IdentityIndex


def _bibliography(source: str) -> Bibliography:
    library = bibtexparser.parse_string(source)
    return Bibliography(library.blocks, IdentityIndex(library.entries))


def test_audit_identifies_safe_normalization_actions() -> None:
    bibliography = _bibliography(
        """\
@article{legacy,
  author = {Macrì , Emanuele},
  title = {Article},
  journal = {J. Tests},
  fjournal = {Journal of Tests},
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
    assert findings[("book-pages-total", ("pages",))].fix_action == "book-pagination"
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

    finding = next(
        finding for finding in result.findings if finding.code == "ambiguous-journal-field"
    )
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
  journal = {Old abbreviation},
  shortjournal = {Different abbreviation}
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
    assert findings["book-pagination-conflict"].fix_action is None


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

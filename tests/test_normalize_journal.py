"""Tests for the explicitly accepted MR journal-pair convention."""

import bibtexparser
import pytest

from biblio.bibliography import Bibliography, IdentityIndex
from biblio.normalize.journal import normalize_journal_fields


def _bibliography(source: str) -> Bibliography:
    library = bibtexparser.parse_string(source)
    assert not library.failed_blocks
    return Bibliography(library.blocks, IdentityIndex(library.entries))


def _snapshot(bibliography: Bibliography) -> tuple[tuple[tuple[str, str], ...], ...]:
    return tuple(
        tuple((field.key, str(field.value)) for field in entry.fields) for entry in bibliography
    )


def test_complete_pair_migrates_in_place_with_exact_values() -> None:
    bibliography = _bibliography(
        r"@article{one,title={Title},journal={ J. {\"O} Test },author={Doe},"
        r"fjournal={ Journal of {\"O} Tests },year={2020},mrnumber={123456}}"
    )

    report = normalize_journal_fields(bibliography)

    assert not report.conflicts
    assert not report.ambiguous
    assert report.changes.changed_keys == ("one",)
    assert _snapshot(bibliography) == (
        (
            ("title", "Title"),
            ("shortjournal", r" J. {\"O} Test "),
            ("author", "Doe"),
            ("journaltitle", r" Journal of {\"O} Tests "),
            ("year", "2020"),
            ("mrnumber", "123456"),
        ),
    )
    assert [(delta.field, delta.before, delta.after) for delta in report.changes.field_deltas] == [
        ("journal", r" J. {\"O} Test ", None),
        ("shortjournal", None, r" J. {\"O} Test "),
        ("fjournal", r" Journal of {\"O} Tests ", None),
        ("journaltitle", None, r" Journal of {\"O} Tests "),
    ]


@pytest.mark.parametrize(
    "fields, source, target",
    [
        ("journal={Journal of Tests}", "journal", "shortjournal"),
        ("journal={Journal of Tests},shortjournal={Journal of Tests}", "journal", "shortjournal"),
        ("journal={Journal of Tests},shortjournal={J. Tests}", "journal", "shortjournal"),
        ("journal={Journal of Tests},journaltitle={Journal of Tests}", "journal", "shortjournal"),
        ("fjournal={Journal of Tests}", "fjournal", "journaltitle"),
        ("fjournal={Journal of Tests},journaltitle={Journal of Tests}", "fjournal", "journaltitle"),
        ("fjournal={Journal of Tests},journaltitle={Other Journal}", "fjournal", "journaltitle"),
    ],
)
@pytest.mark.parametrize("marker", ["", ",mrnumber={123456}"])
def test_lone_source_is_preserved_even_with_equal_target(
    fields: str, source: str, target: str, marker: str
) -> None:
    bibliography = _bibliography(f"@article{{one,{fields}{marker}}}")
    before = _snapshot(bibliography)

    report = normalize_journal_fields(bibliography)

    assert _snapshot(bibliography) == before
    assert not report.changes.changed
    assert not report.conflicts
    assert report.ambiguous == (("one", source, target),)


@pytest.mark.parametrize(
    "extra, conflict",
    [
        ("shortjournal={Other}", ("one", "journal", "shortjournal")),
        ("journaltitle={Other}", ("one", "fjournal", "journaltitle")),
        ("shortjournal={J. Tests},journaltitle={Other}", ("one", "fjournal", "journaltitle")),
        ("SHORTJOURNAL={ J. Tests}", ("one", "journal", "shortjournal")),
    ],
)
def test_target_conflict_preserves_the_entire_pair(
    extra: str, conflict: tuple[str, str, str]
) -> None:
    bibliography = _bibliography(
        f"@article{{one,journal={{J. Tests}},fjournal={{Journal of Tests}},"
        f"{extra},mrnumber={{123456}}}}"
    )
    before = _snapshot(bibliography)

    report = normalize_journal_fields(bibliography)

    assert _snapshot(bibliography) == before
    assert not report.changes.changed
    assert report.conflicts == (conflict,)
    assert not report.ambiguous


def test_equal_targets_remove_only_legacy_pair() -> None:
    bibliography = _bibliography(
        "@article{one,SHORTJOURNAL={J. Tests},JOURNAL={J. Tests},title={Title},"
        "FJOURNAL={Journal of Tests},JournalTitle={Journal of Tests},mrnumber={123456}}"
    )

    report = normalize_journal_fields(bibliography)

    assert _snapshot(bibliography) == (
        (
            ("SHORTJOURNAL", "J. Tests"),
            ("title", "Title"),
            ("JournalTitle", "Journal of Tests"),
            ("mrnumber", "123456"),
        ),
    )
    assert report.changes.changed_keys == ("one",)
    assert [delta.field for delta in report.changes.field_deltas] == ["journal", "fjournal"]
    assert all(delta.after is None for delta in report.changes.field_deltas)


def test_case_insensitive_pair_migrates_and_is_idempotent() -> None:
    bibliography = _bibliography(
        "@article{one,JOURNAL={J. Tests},FJournal={Journal of Tests},MRCLASS={14J32}}"
    )
    assert normalize_journal_fields(bibliography).changes.changed_keys == ("one",)
    assert _snapshot(bibliography) == (
        (
            ("shortjournal", "J. Tests"),
            ("journaltitle", "Journal of Tests"),
            ("MRCLASS", "14J32"),
        ),
    )
    second = normalize_journal_fields(bibliography)
    assert not second.changes.changed
    assert not second.conflicts
    assert not second.ambiguous


@pytest.mark.parametrize("journal, fjournal", [("", "Full"), ("Abbr.", " "), ("", "")])
def test_empty_source_preserves_pair_for_review(journal: str, fjournal: str) -> None:
    bibliography = _bibliography(
        f"@article{{one,journal={{{journal}}},fjournal={{{fjournal}}},mrnumber={{123456}}}}"
    )
    before = _snapshot(bibliography)
    report = normalize_journal_fields(bibliography)
    assert _snapshot(bibliography) == before
    assert not report.changes.changed
    assert report.ambiguous == (
        ("one", "journal", "shortjournal"),
        ("one", "fjournal", "journaltitle"),
    )


@pytest.mark.parametrize(
    "duplicate",
    ["journal", "fjournal", "shortjournal", "journaltitle", "mrnumber", "mrclass", "mrreviewer"],
)
def test_duplicate_participating_fields_fail_before_any_mutation(duplicate: str) -> None:
    bibliography = _bibliography(
        "@article{first,journal={J. Tests},fjournal={Journal of Tests},mrnumber={123456}}\n"
        f"@article{{second,{duplicate}={{One}},{duplicate.upper()}={{Two}}}}"
    )
    before = _snapshot(bibliography)
    with pytest.raises(ValueError, match=f"duplicate '{duplicate}' fields"):
        normalize_journal_fields(bibliography)
    assert _snapshot(bibliography) == before


def test_two_conflicts_are_reported_without_changes() -> None:
    bibliography = _bibliography(
        "@article{one,journal={J. Tests},fjournal={Journal of Tests},"
        "shortjournal={Other},journaltitle={Other Journal},mrnumber={123456}}"
    )
    before = _snapshot(bibliography)
    report = normalize_journal_fields(bibliography)
    assert not report.changes.changed
    assert _snapshot(bibliography) == before
    assert report.conflicts == (
        ("one", "journal", "shortjournal"),
        ("one", "fjournal", "journaltitle"),
    )


def test_one_equal_target_keeps_surviving_field_order() -> None:
    bibliography = _bibliography(
        "@article{one,fjournal={Full},title={Title},shortjournal={Short},journal={Short},mrnumber={123456}}"
    )
    report = normalize_journal_fields(bibliography)
    assert report.changes.changed_keys == ("one",)
    assert _snapshot(bibliography) == (
        (
            ("journaltitle", "Full"),
            ("title", "Title"),
            ("shortjournal", "Short"),
            ("mrnumber", "123456"),
        ),
    )


def test_pair_convention_does_not_guess_abbreviation_semantics() -> None:
    bibliography = _bibliography(
        "@article{one,journal={Not abbreviated},fjournal={J. Full},mrnumber={123456}}"
    )
    report = normalize_journal_fields(bibliography)
    assert report.changes.changed_keys == ("one",)
    assert _snapshot(bibliography) == (
        (("shortjournal", "Not abbreviated"), ("journaltitle", "J. Full"), ("mrnumber", "123456")),
    )


def test_empty_existing_target_is_a_conflict_not_permission_to_overwrite() -> None:
    bibliography = _bibliography(
        "@article{one,journal={Short},fjournal={Full},journaltitle={},mrnumber={123456}}"
    )
    before = _snapshot(bibliography)
    report = normalize_journal_fields(bibliography)
    assert report.conflicts == (("one", "fjournal", "journaltitle"),)
    assert not report.changes.changed
    assert _snapshot(bibliography) == before


@pytest.mark.parametrize(
    "marker",
    [
        "",
        ",mrnumber={}",
        ",MRCLASS={ }",
        ",mrreviewer={\t}",
        ",mri={123456}",
        ",mrnumber_extra={123456}",
        ",title={MR123456}",
        ",shortjournal={J. Tests},journaltitle={Journal of Tests}",
    ],
)
def test_pair_without_nonempty_exact_mr_marker_is_preserved(marker: str) -> None:
    bibliography = _bibliography(
        f"@article{{MR123456,journal={{J. Tests}},fjournal={{Journal of Tests}}{marker}}}"
    )
    before = _snapshot(bibliography)
    report = normalize_journal_fields(bibliography)
    assert _snapshot(bibliography) == before
    assert not report.changes.changed
    assert not report.conflicts
    assert report.ambiguous == (
        ("MR123456", "journal", "shortjournal"),
        ("MR123456", "fjournal", "journaltitle"),
    )


@pytest.mark.parametrize(
    "marker", ["mrnumber", "mrclass", "mrreviewer", "MRNUMBER", "MRCLASS", "MRREVIEWER"]
)
def test_each_exact_mr_marker_enables_same_pair_and_preserves_its_value(marker: str) -> None:
    marker_value = "  explicit local marker  "
    bibliography = _bibliography(
        f"@article{{one,{marker}={{{marker_value}}},"
        "journal={J. Tests},fjournal={Journal of Tests}}"
    )
    report = normalize_journal_fields(bibliography)
    assert report.changes.changed_keys == ("one",)
    assert _snapshot(bibliography) == (
        (
            (marker, marker_value),
            ("shortjournal", "J. Tests"),
            ("journaltitle", "Journal of Tests"),
        ),
    )
    assert not normalize_journal_fields(bibliography).changes.changed

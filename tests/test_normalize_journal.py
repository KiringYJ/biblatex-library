"""Tests for lossless legacy journal-field migration."""

import bibtexparser

from biblio.bibliography import Bibliography, IdentityIndex
from biblio.normalize.journal import normalize_journal_fields


def _bibliography(source: str) -> Bibliography:
    library = bibtexparser.parse_string(source)
    return Bibliography(library.blocks, IdentityIndex(library.entries))


def test_legacy_pair_is_renamed_without_changing_values() -> None:
    bibliography = _bibliography("@article{one,journal={J. Test},fjournal={Journal of Tests}}\n")

    report = normalize_journal_fields(bibliography)

    fields = bibliography.resolve("one").fields_dict
    assert report.conflicts == ()
    assert report.changes.changed_keys == ("one",)
    assert "journal" not in fields
    assert "fjournal" not in fields
    assert fields["shortjournal"].value == "J. Test"
    assert fields["journaltitle"].value == "Journal of Tests"


def test_redundant_legacy_field_is_removed() -> None:
    bibliography = _bibliography("@article{one,journal={J. Test},shortjournal={J. Test}}\n")

    report = normalize_journal_fields(bibliography)

    fields = bibliography.resolve("one").fields_dict
    assert report.changes.changed
    assert "journal" not in fields
    assert fields["shortjournal"].value == "J. Test"


def test_conflicting_target_is_preserved_for_manual_review() -> None:
    bibliography = _bibliography("@article{one,journal={Legacy},shortjournal={Current}}\n")

    report = normalize_journal_fields(bibliography)

    fields = bibliography.resolve("one").fields_dict
    assert report.changes.changed is False
    assert report.conflicts == (("one", "journal", "shortjournal"),)
    assert report.ambiguous == ()
    assert fields["journal"].value == "Legacy"
    assert fields["shortjournal"].value == "Current"


def test_journal_normalization_is_idempotent() -> None:
    bibliography = _bibliography("@article{one,journal={J. Test},fjournal={Journal of Tests}}\n")

    normalize_journal_fields(bibliography)

    assert normalize_journal_fields(bibliography).changes.changed is False


def test_journal_without_full_or_short_context_is_left_for_review() -> None:
    bibliography = _bibliography("@article{one,journal={Journal of Tests}}\n")

    report = normalize_journal_fields(bibliography)

    assert report.changes.changed is False
    assert report.ambiguous == (("one", "journal", "shortjournal"),)
    assert "journal" in bibliography.resolve("one").fields_dict

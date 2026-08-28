"""Tests for pure eprint normalization."""

import bibtexparser
import pytest

from biblio.bibliography import Bibliography, IdentityIndex
from biblio.normalize.eprint import normalize_eprint_fields


def _bibliography(source: str) -> Bibliography:
    library = bibtexparser.parse_string(source)
    return Bibliography(library.blocks, IdentityIndex(library.entries))


def test_normalizes_legacy_arxiv_fields_without_changing_entry_type() -> None:
    bibliography = _bibliography(
        "@misc{one, archiveprefix={arXiv}, primaryclass={cs.LO}}\n"
        "@misc{two, archiveprefix={HAL}, primaryclass={math.GM}, eprinttype={HAL}}\n"
    )

    report = normalize_eprint_fields(bibliography)

    assert report.renamed_type == ("one", "two")
    assert report.renamed_class == ("one", "two")
    assert report.normalized_type == ("one",)
    one = bibliography.resolve("one")
    assert one.entry_type == "misc"
    assert one.fields_dict["eprinttype"].value == "arxiv"
    assert one.fields_dict["eprintclass"].value == "cs.LO"
    two = bibliography.resolve("two")
    assert two.entry_type == "misc"
    assert two.fields_dict["eprinttype"].value == "HAL"


def test_eprint_normalization_is_idempotent() -> None:
    bibliography = _bibliography("@online{one, eprinttype={arxiv}, eprint={1234.5}}\n")

    assert normalize_eprint_fields(bibliography).changes.changed is False


@pytest.mark.parametrize(
    ("fields", "conflict"),
    [
        (
            "archiveprefix={arXiv},EPRINTTYPE={HAL},primaryclass={math.AG}",
            ("one", "archiveprefix", "eprinttype"),
        ),
        (
            "archiveprefix={arXiv},primaryclass={math.AG},EPRINTCLASS={math.DG}",
            ("one", "primaryclass", "eprintclass"),
        ),
    ],
)
def test_conflicts_preserve_entire_alias_namespace(
    fields: str, conflict: tuple[str, str, str]
) -> None:
    bibliography = _bibliography(f"@misc{{one,{fields}}}")
    before = tuple((field.key, field.value) for field in bibliography.resolve("one").fields)
    report = normalize_eprint_fields(bibliography)
    assert not report.changes.changed
    assert report.conflicts == (conflict,)
    assert tuple((field.key, field.value) for field in bibliography.resolve("one").fields) == before


def test_equal_aliases_only_remove_legacy_fields() -> None:
    bibliography = _bibliography(
        "@misc{one,ARCHIVEPREFIX={arXiv},EPRINTTYPE={arxiv},"
        "PRIMARYCLASS={math.AG},EPRINTCLASS={math.AG}}"
    )
    report = normalize_eprint_fields(bibliography)
    assert not report.conflicts
    assert [(field.key, field.value) for field in bibliography.resolve("one").fields] == [
        ("EPRINTTYPE", "arxiv"),
        ("EPRINTCLASS", "math.AG"),
    ]
    assert all(delta.after is None for delta in report.changes.field_deltas)


def test_arbitrary_type_case_differences_remain_conflicts() -> None:
    bibliography = _bibliography("@misc{one,archiveprefix={HAL},eprinttype={hal}}")
    report = normalize_eprint_fields(bibliography)
    assert report.conflicts == (("one", "archiveprefix", "eprinttype"),)
    assert not report.changes.changed


def test_alias_migration_is_idempotent() -> None:
    bibliography = _bibliography("@misc{one,ARCHIVEPREFIX={arXiv},PRIMARYCLASS={math.AG}}")
    assert normalize_eprint_fields(bibliography).changes.changed
    assert not normalize_eprint_fields(bibliography).changes.changed

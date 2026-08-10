"""Tests for pure eprint normalization."""

import bibtexparser

from biblio.bibliography import Bibliography, IdentityIndex
from biblio.normalize.eprint import normalize_eprint_fields


def _bibliography(source: str) -> Bibliography:
    library = bibtexparser.parse_string(source)
    return Bibliography(library.blocks, IdentityIndex(library.entries))


def test_normalizes_legacy_arxiv_fields_and_entry_type() -> None:
    bibliography = _bibliography(
        "@misc{one, archiveprefix={arXiv}, primaryclass={cs.LO}}\n"
        "@misc{two, archiveprefix={HAL}, primaryclass={math.GM}, eprinttype={HAL}}\n"
    )

    report = normalize_eprint_fields(bibliography)

    assert report.renamed_type == ("one", "two")
    assert report.renamed_class == ("one", "two")
    assert report.normalized_type == ("one",)
    assert report.changed_entry_type == ("one",)
    one = bibliography.resolve("one")
    assert one.entry_type == "online"
    assert one.fields_dict["eprinttype"].value == "arxiv"
    assert one.fields_dict["eprintclass"].value == "cs.LO"
    two = bibliography.resolve("two")
    assert two.entry_type == "misc"
    assert two.fields_dict["eprinttype"].value == "HAL"


def test_eprint_normalization_is_idempotent() -> None:
    bibliography = _bibliography("@online{one, eprinttype={arxiv}, eprint={1234.5}}\n")

    assert normalize_eprint_fields(bibliography).changes.changed is False

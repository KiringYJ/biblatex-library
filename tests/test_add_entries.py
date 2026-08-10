"""Tests for `.bib`-only staging preparation and pure append."""

import hashlib
from pathlib import Path

import bibtexparser
import pytest

from biblio.add_entries import (
    discover_staged_bib_files,
    parse_staged_entries,
    prepare_entries,
)
from biblio.bibliography import Bibliography, IdentityIndex
from biblio.lifecycle import add


def _bibliography(source: str) -> Bibliography:
    library = bibtexparser.parse_string(source)
    assert not library.failed_blocks
    return Bibliography(library.blocks, IdentityIndex(library.entries))


def test_discovery_accepts_only_bib_and_sorts_by_filename(tmp_path: Path) -> None:
    (tmp_path / "b.bib").write_text("@book{x,title={X}}", encoding="utf-8")
    (tmp_path / "a.BIB").write_text("@book{x,title={X}}", encoding="utf-8")
    (tmp_path / "a.json").write_text("{}", encoding="utf-8")

    assert [path.name for path in discover_staged_bib_files(tmp_path)] == ["a.BIB", "b.bib"]


def test_parse_and_prepare_preserve_file_and_physical_entry_order(tmp_path: Path) -> None:
    first = tmp_path / "a.bib"
    second = tmp_path / "b.bib"
    first.write_text(
        "@book{one,author={Alpha, A},date={2020},title={One},isbn={123}}\n"
        "@book{two,author={Beta, B},date={2021},title={Two},url={https://two}}\n",
        encoding="utf-8",
    )
    second.write_text(
        "@article{three,author={Gamma, G},date={2022},title={Three},doi={10.1/three}}\n",
        encoding="utf-8",
    )

    prepared = prepare_entries(parse_staged_entries((first, second)))

    assert [entry.key.split("-", 1)[0] for entry in prepared] == ["alpha", "beta", "gamma"]
    assert prepared[0].key.endswith(hashlib.sha256(b"123").hexdigest()[:8])
    assert prepared[2].key.endswith(hashlib.sha256(b"10.1/three").hexdigest()[:8])


def test_prepare_uses_arxiv_eprint_as_exact_identifier() -> None:
    entries = bibtexparser.parse_string(
        "@online{x,author={Doe, Jane},date={2020},title={X},"
        "eprint={2101.00001v2},eprinttype={arxiv}}"
    ).entries

    prepared = prepare_entries(entries)

    expected = hashlib.sha256(b"2101.00001v2").hexdigest()[:8]
    assert prepared[0].key == f"doe-2020-{expected}"


def test_prepare_preserves_shorthand_and_editor_fallback_semantics() -> None:
    entries = bibtexparser.parse_string(
        "@book{one,shorthand={ÉGA IV},editor={Ignored, Editor},year={1964},isbn={123}}"
        "@book{two,editor={Editor, Erin},sortname={Sorting Name},date={2021-05},url={u}}"
    ).entries

    prepared = prepare_entries(entries)

    assert prepared[0].key.startswith("egaiv-1964-")
    assert prepared[1].key.startswith("editor-2021-")


def test_matching_derived_arxiv_doi_hashes_eprint_not_doi() -> None:
    entry = bibtexparser.parse_string(
        "@online{x,author={Doe, Jane},date={2020},eprint={2101.00001},"
        "eprinttype={arxiv},doi={10.48550/arXiv.2101.00001}}"
    ).entries[0]

    prepared = prepare_entries((entry,))

    expected = hashlib.sha256(b"2101.00001").hexdigest()[:8]
    assert prepared[0].key == f"doe-2020-{expected}"
    assert prepared[0].fields_dict["doi"].value == "10.48550/arXiv.2101.00001"


def test_spaced_arxiv_marker_still_selects_eprint_for_derived_doi() -> None:
    entry = bibtexparser.parse_string(
        "@online{x,author={Doe, Jane},date={2020},eprint={2101.00001},"
        "eprinttype={ arXiv },doi={10.48550/arXiv.2101.00001}}"
    ).entries[0]

    prepared = prepare_entries((entry,))

    expected = hashlib.sha256(b"2101.00001").hexdigest()[:8]
    assert prepared[0].key == f"doe-2020-{expected}"


def test_distinct_publisher_doi_remains_primary_for_arxiv_entry() -> None:
    entry = bibtexparser.parse_string(
        "@online{x,author={Doe, Jane},date={2020},eprint={2101.00001},"
        "eprinttype={arxiv},doi={10.1000/published}}"
    ).entries[0]

    prepared = prepare_entries((entry,))

    expected = hashlib.sha256(b"10.1000/published").hexdigest()[:8]
    assert prepared[0].key == f"doe-2020-{expected}"


@pytest.mark.parametrize("field", ["hdl", "acmdl_doi"])
def test_extended_primary_identifiers_have_stable_fallback_priority(field: str) -> None:
    value = f"value/{field}"
    entry = bibtexparser.parse_string(
        f"@online{{x,author={{Doe, Jane}},date={{2020}},{field}={{{value}}},url={{fallback}}}}"
    ).entries[0]

    prepared = prepare_entries((entry,))

    expected = hashlib.sha256(value.encode()).hexdigest()[:8]
    assert prepared[0].key == f"doe-2020-{expected}"


def test_lifecycle_add_appends_without_reordering_existing_blocks() -> None:
    bibliography = _bibliography("@book{old-2020-00000000,title={Old}}\n@comment{tail}\n")
    comment = bibliography.blocks[1]
    new_entry = _bibliography("@book{new-2021-11111111,title={New}}\n").resolve("new-2021-11111111")

    result = add(bibliography, (new_entry,))

    assert result.added_keys == ("new-2021-11111111",)
    assert bibliography.blocks[1] is comment
    assert [entry.key for entry in bibliography] == [
        "old-2020-00000000",
        "new-2021-11111111",
    ]


def test_lifecycle_add_preflights_complete_namespace_before_mutating() -> None:
    bibliography = _bibliography("@book{old-2020-00000000,title={Old}}\n")
    colliding = _bibliography("@book{old-2020-00000000,title={Collision}}\n").resolve(
        "old-2020-00000000"
    )
    unique = _bibliography("@book{new-2021-11111111,title={New}}\n").resolve("new-2021-11111111")

    with pytest.raises(ValueError, match="duplicate canonical key"):
        add(bibliography, (unique, colliding))

    assert [entry.key for entry in bibliography] == ["old-2020-00000000"]

"""Derived arXiv DOI cleanup must preserve nonredundant identifier information."""

import bibtexparser
import pytest

from biblio.bibliography import Bibliography, IdentityIndex
from biblio.normalize.pipeline import normalize_bibliography


def _bibliography(source: str) -> Bibliography:
    library = bibtexparser.parse_string(source)
    assert not library.failed_blocks
    return Bibliography(library.blocks, IdentityIndex(library.entries))


@pytest.mark.parametrize("action", ["all", "arxiv-doi"])
def test_collins_entry_removes_only_the_matching_derived_doi(action: str) -> None:
    key = "collins-2025-74457091"
    bibliography = _bibliography(
        f"@online{{{key},"
        "title={An Introduction to Conifold Transitions},author={Collins, Tristan C.},"
        "date={2025},eprint={2509.01002},eprinttype={arxiv},eprintclass={math.DG},"
        "doi={10.48550/arxiv.2509.01002}}"
    )
    entry = bibliography.resolve(key)
    expected = tuple((field.key, field.value) for field in entry.fields if field.key != "doi")

    result = normalize_bibliography(bibliography, action)

    assert entry.key == key
    assert entry.entry_type == "online"
    assert tuple((field.key, field.value) for field in entry.fields) == expected
    assert result.changes.changed_keys == (key,)
    assert [(delta.field, delta.before, delta.after) for delta in result.changes.field_deltas] == [
        ("doi", "10.48550/arxiv.2509.01002", None)
    ]
    assert not normalize_bibliography(bibliography, action).changes.changed


@pytest.mark.parametrize(
    "doi, eprint",
    [
        ("10.48550/ARXIV.2509.01002", "2509.01002"),
        ("10.48550/arxiv.2509.01002V2", "2509.01002v2"),
        ("10.48550/arxiv.math.ag/0301001v2", "math.AG/0301001v2"),
        ("10.48550/arxiv.2509.01002", "arXiv:2509.01002"),
        ("doi:10.48550/arXiv.2509.01002", "2509.01002"),
        ("https://doi.org/10.48550/arXiv.2509.01002", "2509.01002"),
        ("http://dx.doi.org/10.48550/arXiv.2509.01002", "2509.01002"),
        ("HTTPS://DOI.ORG/10.48550/%61rXiv.2509.01002", "2509.01002"),
    ],
)
def test_supported_derived_doi_forms_preserve_exact_eprint(doi: str, eprint: str) -> None:
    bibliography = _bibliography(
        f"@article{{one,DOI={{{doi}}},EPRINT={{{eprint}}},EPRINTTYPE={{arXiv}}}}"
    )

    result = normalize_bibliography(bibliography, "arxiv-doi")

    entry = bibliography.resolve("one")
    assert result.changes.changed_keys == ("one",)
    assert "DOI" not in entry.fields_dict
    assert entry.fields_dict["EPRINT"].value == eprint
    assert entry.fields_dict["EPRINTTYPE"].value == "arXiv"
    assert entry.entry_type == "article"
    assert result.changes.field_deltas[0].before == doi


@pytest.mark.parametrize(
    "marker",
    [
        "eprinttype={arxiv}",
        "ARCHIVEPREFIX={ARXIV}",
        "archiveprefix={arXiv},EPRINTTYPE={arxiv}",
    ],
)
def test_explicit_consistent_arxiv_markers_authorize_doi_cleanup(marker: str) -> None:
    bibliography = _bibliography(
        f"@misc{{one,{marker},eprint={{2509.01002}},doi={{10.48550/arxiv.2509.01002}}}}"
    )

    result = normalize_bibliography(bibliography, "arxiv-doi")

    assert result.changes.changed_keys == ("one",)
    assert "doi" not in bibliography.resolve("one").fields_dict
    assert bibliography.resolve("one").entry_type == "misc"


@pytest.mark.parametrize(
    "fields",
    [
        "eprint={2509.01002},doi={10.48550/arxiv.2509.01002}",
        "eprinttype={HAL},eprint={2509.01002},doi={10.48550/arxiv.2509.01002}",
        "eprinttype={},eprint={2509.01002},doi={10.48550/arxiv.2509.01002}",
        "eprinttype={arxiv},doi={10.48550/arxiv.2509.01002}",
        "eprinttype={arxiv},eprint={},doi={10.48550/arxiv.}",
        "eprinttype={arxiv},eprint={2509.01002}",
        "eprinttype={arxiv},eprint={2509.01002},doi={10.1000/published}",
        "eprinttype={arxiv},eprint={2509.01003},doi={10.48550/arxiv.2509.01002}",
        "eprinttype={arxiv},eprint={2509.01002v2},doi={10.48550/arxiv.2509.01002}",
        "eprinttype={arxiv},eprint={2509.01002},doi={10.48550/arxiv.2509.01002v2}",
        "eprinttype={arxiv},eprint={2509.01002v1},doi={10.48550/arxiv.2509.01002v2}",
        "eprinttype={arxiv},eprint={ 2509.01002 },doi={10.48550/arxiv.2509.01002}",
        "eprinttype={arxiv},eprint={math.K/0301001},doi={10.48550/arxiv.math.K/0301001}",
        r"eprinttype={arxiv},eprint={\identifier},doi={10.48550/arxiv.\identifier}",
    ],
)
def test_unproven_or_unsupported_redundancy_preserves_all_fields(fields: str) -> None:
    bibliography = _bibliography(f"@online{{one,{fields}}}")
    entry = bibliography.resolve("one")
    before = tuple((field.key, field.value) for field in entry.fields)

    result = normalize_bibliography(bibliography, "arxiv-doi")

    assert not result.changes.changed
    assert tuple((field.key, field.value) for field in entry.fields) == before


@pytest.mark.parametrize("action", ["all", "arxiv-doi"])
@pytest.mark.parametrize(
    "aliases",
    [
        "eprinttype={arxiv},archiveprefix={HAL}",
        "eprinttype={HAL},archiveprefix={arxiv}",
        "eprinttype={arxiv},eprintclass={math.DG},primaryclass={math.AG}",
    ],
)
def test_conflicting_eprint_aliases_block_doi_cleanup(action: str, aliases: str) -> None:
    bibliography = _bibliography(
        f"@online{{one,{aliases},eprint={{2509.01002}},doi={{10.48550/arxiv.2509.01002}}}}"
    )
    entry = bibliography.resolve("one")
    before = tuple((field.key, field.value) for field in entry.fields)

    result = normalize_bibliography(bibliography, action)

    assert not result.changes.changed
    assert tuple((field.key, field.value) for field in entry.fields) == before


@pytest.mark.parametrize(
    "doi",
    [
        "https://doi.org/10.48550/arxiv.2509.01002?download=1",
        "https://doi.org/10.48550/arxiv.2509.01002?",
        "https://doi.org/10.48550/arxiv.2509.01002#part",
        "https://doi.org/10.48550/arxiv.2509.01002#",
        "https://doi.org:443/10.48550/arxiv.2509.01002",
        "https://user@doi.org/10.48550/arxiv.2509.01002",
        "https://doi.org.example.test/10.48550/arxiv.2509.01002",
        "https://doi.org/10.48550/arxiv.2509.01002%ZZ",
        "10.48550/arxiv.2509.01002/",
        " 10.48550/arxiv.2509.01002 ",
        "\x00https://doi.org/10.48550/arxiv.2509.01002",
    ],
)
def test_doi_components_and_unsupported_wrappers_are_preserved(doi: str) -> None:
    bibliography = _bibliography(
        f"@online{{one,eprinttype={{arxiv}},eprint={{2509.01002}},doi={{{doi}}}}}"
    )

    assert not normalize_bibliography(bibliography, "arxiv-doi").changes.changed
    assert bibliography.resolve("one").fields_dict["doi"].value == doi


@pytest.mark.parametrize(
    "url, removed",
    [
        ("https://doi.org/10.48550/arxiv.2509.01002", True),
        ("https://arxiv.org/abs/2509.01002", True),
        ("https://arxiv.org/pdf/2509.01002", False),
        ("https://doi.org/10.48550/arxiv.2509.01002?download=1", False),
        ("https://example.test/paper", False),
    ],
)
def test_all_cleans_urls_before_doi_without_losing_url_information(url: str, removed: bool) -> None:
    bibliography = _bibliography(
        "@online{one,eprinttype={arxiv},eprint={2509.01002},"
        f"doi={{10.48550/arxiv.2509.01002}},url={{{url}}}}}"
    )

    result = normalize_bibliography(bibliography, "all")

    fields = bibliography.resolve("one").fields_dict
    assert "doi" not in fields
    assert ("url" not in fields) is removed
    if not removed:
        assert fields["url"].value == url
    assert [delta.field for delta in result.changes.field_deltas] == (
        ["url", "doi"] if removed else ["doi"]
    )
    assert not normalize_bibliography(bibliography, "all").changes.changed


@pytest.mark.parametrize("action", ["all", "arxiv-doi"])
@pytest.mark.parametrize("duplicate", ["doi", "eprint", "eprinttype", "archiveprefix"])
def test_duplicate_fields_fail_before_any_doi_removal(action: str, duplicate: str) -> None:
    bibliography = _bibliography(
        "@online{first,eprinttype={arxiv},eprint={2509.01002},"
        "doi={10.48550/arxiv.2509.01002}}"
        f"@online{{second,{duplicate}={{One}},{duplicate.upper()}={{Two}}}}"
    )

    with pytest.raises(ValueError, match=f"duplicate '{duplicate}' fields"):
        normalize_bibliography(bibliography, action)

    assert "doi" in bibliography.resolve("first").fields_dict

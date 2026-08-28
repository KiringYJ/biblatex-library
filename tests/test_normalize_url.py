"""Tests for pure redundant-URL normalization."""

import bibtexparser
import pytest

from biblio.bibliography import Bibliography, IdentityIndex
from biblio.normalize.url import normalize_trivial_urls


def _bibliography(source: str) -> Bibliography:
    library = bibtexparser.parse_string(source)
    return Bibliography(library.blocks, IdentityIndex(library.entries))


@pytest.mark.parametrize(
    "url",
    [
        "https://doi.org/10.1000/xyz",
        "http://doi.org/10.1000/xyz",
        "https://dx.doi.org/10.1000/xyz",
        "http://dx.doi.org/10.1000/xyz",
    ],
)
def test_removes_matching_doi_resolver_urls(url: str) -> None:
    bibliography = _bibliography(f"@article{{paper, doi={{10.1000/xyz}}, url={{{url}}}}}\n")

    report = normalize_trivial_urls(bibliography)

    assert report.removed == ("paper",)
    assert "url" not in bibliography.resolve("paper").fields_dict
    assert report.changes.field_deltas[0].before == url


def test_removes_only_matching_typed_arxiv_url() -> None:
    bibliography = _bibliography(
        "@online{match, eprint={2602.21791}, eprinttype={arxiv}, "
        "url={https://arxiv.org/abs/2602.21791}}\n"
        "@online{different, eprint={2602.21792}, eprinttype={arxiv}, "
        "url={https://arxiv.org/abs/2602.21791}}\n"
        "@online{untyped, eprint={2602.21791}, "
        "url={https://arxiv.org/abs/2602.21791}}\n"
    )

    report = normalize_trivial_urls(bibliography)

    assert report.removed == ("match",)
    assert "url" not in bibliography.resolve("match").fields_dict
    assert "url" in bibliography.resolve("different").fields_dict
    assert "url" in bibliography.resolve("untyped").fields_dict


def test_preserves_nonredundant_urls_and_reports_noop() -> None:
    bibliography = _bibliography(
        "@article{custom, doi={10.1000/xyz}, url={https://example.test/paper}}\n"
    )

    report = normalize_trivial_urls(bibliography)

    assert report.removed == ()
    assert report.changes.changed is False


@pytest.mark.parametrize(
    "url",
    [
        "https://arxiv.org/pdf/2602.21791.pdf",
        "https://arxiv.org/abs/2602.21791?download=1",
        "https://arxiv.org/abs/2602.21791#page=1",
        "https://arxiv.org:443/abs/2602.21791",
        "https://user@arxiv.org/abs/2602.21791",
        "https://arxiv.org/ABS/2602.21791",
        "https://arxiv.org/abs/2602.21791/",
        "https://arxiv.org/abs/2602.21791v2",
        "https://doi.org/10.1000/xyz/",
        " https://doi.org/10.1000/xyz ",
    ],
)
def test_preserves_nonexact_url_information(url: str) -> None:
    bibliography = _bibliography(
        f"@online{{one,doi={{10.1000/xyz}},eprinttype={{arxiv}},"
        f"eprint={{2602.21791}},url={{{url}}}}}"
    )
    assert not normalize_trivial_urls(bibliography).changes.changed
    assert bibliography.resolve("one").fields_dict["url"].value == url


def test_conflicting_alias_type_does_not_authorize_removal() -> None:
    bibliography = _bibliography(
        "@misc{one,EPRINTTYPE={arxiv},ARCHIVEPREFIX={HAL},eprint={2602.21791},"
        "url={https://arxiv.org/abs/2602.21791}}"
    )
    assert not normalize_trivial_urls(bibliography).changes.changed


def test_case_sensitive_identifier_is_not_equivalent() -> None:
    bibliography = _bibliography(
        "@misc{one,eprinttype={arxiv},eprint={math.AG/0301001},"
        "url={https://arxiv.org/abs/math.ag/0301001}}"
    )
    assert not normalize_trivial_urls(bibliography).changes.changed


def test_uppercase_field_keys_are_supported() -> None:
    bibliography = _bibliography("@book{one,DOI={10.1000/xyz},URL={https://doi.org/10.1000/xyz}}")
    assert normalize_trivial_urls(bibliography).removed == ("one",)


@pytest.mark.parametrize(
    "prefix",
    [
        "https://arxiv.org/abs/",
        "http://arxiv.org/abs/",
        "https://www.arxiv.org/abs/",
        "http://www.arxiv.org/abs/",
    ],
)
@pytest.mark.parametrize("identifier", ["2602.21791v2", "math.AG/0301001"])
def test_exact_arxiv_links_accept_legacy_type_and_preserve_identifier(
    prefix: str, identifier: str
) -> None:
    bibliography = _bibliography(
        f"@misc{{one,ARCHIVEPREFIX={{arXiv}},EPRINT={{{identifier}}},URL={{{prefix}{identifier}}}}}"
    )
    assert normalize_trivial_urls(bibliography).removed == ("one",)
    assert bibliography.resolve("one").fields_dict["EPRINT"].value == identifier
    assert bibliography.resolve("one").entry_type == "misc"


@pytest.mark.parametrize("identifier", ["10.1000/xyz?download=1", "10.1000/xyz#part"])
def test_component_in_identifier_does_not_authorize_url_deletion(identifier: str) -> None:
    bibliography = _bibliography(
        f"@book{{one,doi={{{identifier}}},url={{https://doi.org/{identifier}}}}}"
    )
    assert not normalize_trivial_urls(bibliography).changes.changed


@pytest.mark.parametrize(
    "prefix",
    ["https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/"],
)
@pytest.mark.parametrize(
    "doi, url_doi",
    [
        ("10.1007/bf01458074", "10.1007/BF01458074"),
        ("10.1007/BF01458074", "10.1007/bf01458074"),
        ("10.1000/Ωabc", "10.1000/ΩABC"),
    ],
)
def test_doi_ascii_equivalence_removes_url_without_rewriting_doi(
    prefix: str, doi: str, url_doi: str
) -> None:
    url = prefix + url_doi
    bibliography = _bibliography(f"@article{{one,DOI={{{doi}}},url={{{url}}}}}")

    result = normalize_trivial_urls(bibliography)

    assert result.removed == ("one",)
    assert bibliography.resolve("one").fields_dict["DOI"].value == doi
    assert "url" not in bibliography.resolve("one").fields_dict
    assert [(delta.field, delta.before, delta.after) for delta in result.changes.field_deltas] == [
        ("url", url, None)
    ]
    assert not normalize_trivial_urls(bibliography).changes.changed


@pytest.mark.parametrize(
    "doi, url_doi",
    [("10.1000/Ω", "10.1000/ω"), ("10.1000/straße", "10.1000/STRASSE"), ("10.1000/K", "10.1000/K")],
)
def test_doi_matching_does_not_fold_non_ascii_case(doi: str, url_doi: str) -> None:
    url = "https://doi.org/" + url_doi
    bibliography = _bibliography(f"@article{{one,doi={{{doi}}},url={{{url}}}}}")
    assert not normalize_trivial_urls(bibliography).changes.changed
    assert bibliography.resolve("one").fields_dict["url"].value == url


@pytest.mark.parametrize(
    "url",
    [
        "https://doi.org/10.1007/BF01458074?download=1",
        "https://doi.org/10.1007/BF01458074?",
        "https://doi.org/10.1007/BF01458074#part",
        "https://doi.org/10.1007/BF01458074#",
        "https://doi.org:443/10.1007/BF01458074",
        "https://user@doi.org/10.1007/BF01458074",
        "https://doi.org.example.test/10.1007/BF01458074",
        "https://doi.org/10.1007/BF01458074/",
        "https://doi.org/10.1007/BF01458074%ZZ",
        "10.1007/BF01458074",
        "doi:10.1007/BF01458074",
    ],
)
def test_doi_equivalence_does_not_discard_url_components(url: str) -> None:
    bibliography = _bibliography(f"@article{{one,doi={{10.1007/bf01458074}},url={{{url}}}}}")
    assert not normalize_trivial_urls(bibliography).changes.changed
    assert bibliography.resolve("one").fields_dict["url"].value == url


@pytest.mark.parametrize(
    "url",
    [
        "HTTPS://DOI.ORG/10.1007/BF01458074",
        "https://www.doi.org/10.1007/BF01458074",
        "https://doi.org/10.1007/%42F01458074",
    ],
)
def test_doi_urls_use_the_existing_approved_resolver_parser(url: str) -> None:
    bibliography = _bibliography(f"@article{{one,doi={{10.1007/bf01458074}},url={{{url}}}}}")
    assert normalize_trivial_urls(bibliography).removed == ("one",)
    assert bibliography.resolve("one").fields_dict["doi"].value == "10.1007/bf01458074"


@pytest.mark.parametrize("control", ["\x00", "\x01", "\x08", "\x1b", "\x7f", "\x80"])
@pytest.mark.parametrize("field", ["doi", "url"])
def test_doi_comparison_preserves_raw_control_prefixed_values(control: str, field: str) -> None:
    doi = control + "https://doi.org/10.1000/xyz" if field == "doi" else "10.1000/xyz"
    url = (
        control + "https://doi.org/10.1000/XYZ" if field == "url" else "https://doi.org/10.1000/XYZ"
    )
    bibliography = _bibliography(f"@article{{one,doi={{{doi}}},url={{{url}}}}}")

    assert not normalize_trivial_urls(bibliography).changes.changed
    assert bibliography.resolve("one").fields_dict["doi"].value == doi
    assert bibliography.resolve("one").fields_dict["url"].value == url

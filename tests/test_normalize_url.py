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
        "http://dx.doi.org/10.1000/xyz/",
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
        "url={https://arxiv.org/pdf/2602.21791.pdf}}\n"
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

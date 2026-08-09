"""Tests for trivial URL removal normalization."""

from __future__ import annotations

from pathlib import Path

import bibtexparser

from biblio.normalize.url import normalize_trivial_urls


def _write_bib(tmp_path: Path, content: str) -> Path:
    bib_path = tmp_path / "library.bib"
    bib_path.write_text(content, encoding="utf-8")
    return bib_path


def test_removes_https_doi_url(tmp_path: Path) -> None:
    bib_path = _write_bib(
        tmp_path,
        """@article{smith2020,
  title = {A Paper},
  doi = {10.1000/xyz},
  url = {https://doi.org/10.1000/xyz}
}
""",
    )

    report = normalize_trivial_urls(bib_path)

    assert report.removed == ["smith2020"]
    library = bibtexparser.parse_file(str(bib_path))
    fields = library.entries[0].fields_dict
    assert "url" not in fields
    assert fields["doi"].value == "10.1000/xyz"


def test_removes_http_doi_url(tmp_path: Path) -> None:
    bib_path = _write_bib(
        tmp_path,
        """@article{jones2021,
  title = {Another Paper},
  doi = {10.2000/abc},
  url = {http://doi.org/10.2000/abc}
}
""",
    )

    report = normalize_trivial_urls(bib_path)

    assert report.removed == ["jones2021"]


def test_removes_dx_doi_url(tmp_path: Path) -> None:
    bib_path = _write_bib(
        tmp_path,
        """@article{lee2019,
  title = {DX Paper},
  doi = {10.3000/def},
  url = {https://dx.doi.org/10.3000/def}
}
""",
    )

    report = normalize_trivial_urls(bib_path)

    assert report.removed == ["lee2019"]


def test_keeps_non_doi_url(tmp_path: Path) -> None:
    bib_path = _write_bib(
        tmp_path,
        """@article{wang2022,
  title = {Custom URL Paper},
  doi = {10.4000/ghi},
  url = {https://example.com/paper.pdf}
}
""",
    )

    report = normalize_trivial_urls(bib_path)

    assert report.removed == []
    library = bibtexparser.parse_file(str(bib_path))
    assert "url" in library.entries[0].fields_dict


def test_keeps_entry_without_doi(tmp_path: Path) -> None:
    bib_path = _write_bib(
        tmp_path,
        """@online{blog2023,
  title = {A Blog Post},
  url = {https://doi.org/10.5000/jkl}
}
""",
    )

    report = normalize_trivial_urls(bib_path)

    assert report.removed == []


def test_keeps_entry_without_url(tmp_path: Path) -> None:
    bib_path = _write_bib(
        tmp_path,
        """@article{nourl2020,
  title = {No URL},
  doi = {10.6000/mno}
}
""",
    )

    report = normalize_trivial_urls(bib_path)

    assert report.removed == []


def test_removes_trailing_slash_url(tmp_path: Path) -> None:
    bib_path = _write_bib(
        tmp_path,
        """@article{slash2021,
  title = {Trailing Slash},
  doi = {10.7000/pqr},
  url = {https://doi.org/10.7000/pqr/}
}
""",
    )

    report = normalize_trivial_urls(bib_path)

    assert report.removed == ["slash2021"]


def test_removes_arxiv_url_matching_explicit_eprint(tmp_path: Path) -> None:
    bib_path = _write_bib(
        tmp_path,
        """@online{ma-2026-6993df98,
  title = {The average order of a connected vertex set in {$K_m \\times P_n$}},
  author = {Ma, Mingyuan and Ren, Han},
  date = {2026},
  eprint = {2602.21791},
  url = {https://arxiv.org/abs/2602.21791},
  eprinttype = {arxiv},
  eprintclass = {math.CO}
}
""",
    )

    report = normalize_trivial_urls(bib_path)

    assert report.removed == ["ma-2026-6993df98"]
    library = bibtexparser.parse_file(str(bib_path))
    fields = library.entries[0].fields_dict
    assert "url" not in fields
    assert fields["eprint"].value == "2602.21791"
    assert fields["eprinttype"].value == "arxiv"


def test_keeps_arxiv_url_when_eprint_differs(tmp_path: Path) -> None:
    bib_path = _write_bib(
        tmp_path,
        """@online{different-preprint,
  title = {A Preprint},
  eprint = {2602.21792},
  eprinttype = {arxiv},
  url = {https://arxiv.org/abs/2602.21791}
}
""",
    )

    report = normalize_trivial_urls(bib_path)

    assert report.removed == []
    library = bibtexparser.parse_file(str(bib_path))
    assert "url" in library.entries[0].fields_dict


def test_keeps_arxiv_url_without_arxiv_eprinttype(tmp_path: Path) -> None:
    bib_path = _write_bib(
        tmp_path,
        """@online{untyped-preprint,
  title = {A Preprint},
  eprint = {2602.21791},
  url = {https://arxiv.org/abs/2602.21791}
}
""",
    )

    report = normalize_trivial_urls(bib_path)

    assert report.removed == []
    library = bibtexparser.parse_file(str(bib_path))
    assert "url" in library.entries[0].fields_dict


def test_dry_run_does_not_modify(tmp_path: Path) -> None:
    content = """@article{dry2020,
  title = {Dry Run},
  doi = {10.8000/stu},
  url = {https://doi.org/10.8000/stu}
}
"""
    bib_path = _write_bib(tmp_path, content)

    report = normalize_trivial_urls(bib_path, dry_run=True)

    assert report.removed == ["dry2020"]
    library = bibtexparser.parse_file(str(bib_path))
    assert "url" in library.entries[0].fields_dict


def test_multiple_entries_mixed(tmp_path: Path) -> None:
    bib_path = _write_bib(
        tmp_path,
        """@article{trivial2020,
  title = {Trivial URL},
  doi = {10.9000/aaa},
  url = {https://doi.org/10.9000/aaa}
}

@article{custom2020,
  title = {Custom URL},
  doi = {10.9000/bbb},
  url = {https://publisher.com/paper}
}

@article{also-trivial2020,
  title = {Also Trivial},
  doi = {10.9000/ccc},
  url = {http://dx.doi.org/10.9000/ccc}
}
""",
    )

    report = normalize_trivial_urls(bib_path)

    assert report.removed == ["trivial2020", "also-trivial2020"]
    library = bibtexparser.parse_file(str(bib_path))
    entries = {e.key: e for e in library.entries}
    assert "url" not in entries["trivial2020"].fields_dict
    assert "url" in entries["custom2020"].fields_dict
    assert "url" not in entries["also-trivial2020"].fields_dict


def test_file_not_found_raises(tmp_path: Path) -> None:
    import pytest

    with pytest.raises(FileNotFoundError):
        normalize_trivial_urls(tmp_path / "nonexistent.bib")

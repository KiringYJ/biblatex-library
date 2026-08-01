"""Tests for identifier template generation."""

from __future__ import annotations

import json
from pathlib import Path

from biblio.config import BiblioConfig
from biblio.template import generate_identifier_template, generate_staging_templates


def _write_bib(tmp_path: Path, content: str) -> Path:
    bib_path = tmp_path / "staging.bib"
    bib_path.write_text(content, encoding="utf-8")
    return bib_path


def test_collapses_equivalent_arxiv_identifiers_to_eprint(tmp_path: Path) -> None:
    config = BiblioConfig.defaults(tmp_path)
    config.staging_dir.mkdir()
    bib_path = config.staging_dir / "pauli.bib"
    bib_path.write_text(
        """@online{pauli2026pcmi,
  author = {Pauli, Sabrina},
  title = {{PCMI} Lecture Notes},
  date = {2026-06-09},
  eprint = {2606.10830},
  eprinttype = {arxiv},
  doi = {10.48550/arXiv.2606.10830},
  url = {https://arxiv.org/abs/2606.10830}
}
""",
        encoding="utf-8",
    )

    processed, generated_files = generate_staging_templates(config)
    template = json.loads(bib_path.with_suffix(".json").read_text(encoding="utf-8"))

    assert processed == 1
    assert generated_files == ["pauli.json"]
    assert template["pauli2026pcmi"] == {
        "main_identifier": "arxiv",
        "identifiers": {"arxiv": "2606.10830"},
    }


def test_removes_arxiv_url_when_eprint_is_canonical(tmp_path: Path) -> None:
    bib_path = _write_bib(
        tmp_path,
        """@online{preprint,
  title = {A Preprint},
  eprint = {2606.10830},
  eprinttype = {arxiv},
  url = {https://arxiv.org/pdf/2606.10830.pdf}
}
""",
    )

    template = generate_identifier_template(bib_path)

    assert template["preprint"] == {
        "main_identifier": "arxiv",
        "identifiers": {"arxiv": "2606.10830"},
    }


def test_keeps_distinct_publisher_doi_and_arxiv_identifier(tmp_path: Path) -> None:
    bib_path = _write_bib(
        tmp_path,
        """@article{published,
  title = {A Published Article},
  eprint = {2606.10830},
  eprinttype = {arxiv},
  doi = {10.1000/published.2606},
  url = {https://arxiv.org/abs/2606.10830}
}
""",
    )

    template = generate_identifier_template(bib_path)

    assert template["published"] == {
        "main_identifier": "doi",
        "identifiers": {
            "doi": "10.1000/published.2606",
            "arxiv": "2606.10830",
        },
    }


def test_keeps_non_equivalent_url(tmp_path: Path) -> None:
    bib_path = _write_bib(
        tmp_path,
        """@online{notes,
  title = {Lecture Notes},
  eprint = {2606.10830},
  eprinttype = {arxiv},
  url = {https://example.org/course/notes}
}
""",
    )

    template = generate_identifier_template(bib_path)

    assert template["notes"] == {
        "main_identifier": "arxiv",
        "identifiers": {
            "url": "https://example.org/course/notes",
            "arxiv": "2606.10830",
        },
    }

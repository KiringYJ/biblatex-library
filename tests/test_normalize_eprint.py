"""Tests for eprint field normalization."""

from __future__ import annotations

from pathlib import Path

import bibtexparser

from biblib.normalize.eprint import normalize_eprint_fields


def _write_bib(tmp_path: Path, content: str) -> Path:
    bib_path = tmp_path / "library.bib"
    bib_path.write_text(content, encoding="utf-8")
    return bib_path


def test_normalize_eprint_fields_updates_entries(tmp_path: Path) -> None:
    bib_content = """@misc{entry-one,
  title = {ArXiv Entry},
  archiveprefix = {arXiv},
  primaryclass = {cs.LO}
}

@misc{entry-two,
  title = {HAL Entry},
  archiveprefix = {HAL},
  primaryclass = {math.GM},
  eprinttype = {HAL}
}
"""
    bib_path = _write_bib(tmp_path, bib_content)

    report = normalize_eprint_fields(bib_path)

    assert report.renamed_type == ["entry-one", "entry-two"]
    assert report.renamed_class == ["entry-one", "entry-two"]
    assert report.normalized_type == ["entry-one"]

    library = bibtexparser.parse_file(str(bib_path))
    entry_one = next(entry for entry in library.entries if entry.key == "entry-one")
    entry_two = next(entry for entry in library.entries if entry.key == "entry-two")

    entry_one_fields = entry_one.fields_dict
    assert "archiveprefix" not in entry_one_fields
    assert "primaryclass" not in entry_one_fields
    assert entry_one_fields["eprinttype"].value == "arxiv"
    assert entry_one_fields["eprintclass"].value == "cs.LO"

    entry_two_fields = entry_two.fields_dict
    assert entry_two_fields["eprinttype"].value == "HAL"
    assert entry_two_fields["eprintclass"].value == "math.GM"
    assert "archiveprefix" not in entry_two_fields
    assert "primaryclass" not in entry_two_fields


def test_normalize_eprint_fields_dry_run(tmp_path: Path) -> None:
    bib_content = """@misc{entry-one,
  title = {Dry Run},
  archiveprefix = {arXiv},
  primaryclass = {cs.LO}
}

@misc{entry-two,
  title = {Dry Run Two},
  archiveprefix = {HAL},
  primaryclass = {math.GM}
}
"""
    bib_path = _write_bib(tmp_path, bib_content)
    before = bib_path.read_text(encoding="utf-8")

    report = normalize_eprint_fields(bib_path, dry_run=True)

    assert report.renamed_type == ["entry-one", "entry-two"]
    assert report.renamed_class == ["entry-one", "entry-two"]
    assert report.normalized_type == ["entry-one"]

    after = bib_path.read_text(encoding="utf-8")
    assert after == before

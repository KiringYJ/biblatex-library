"""Tests for publisher/location normalization."""

from __future__ import annotations

from pathlib import Path

import bibtexparser

from biblib.normalize.publisher import normalize_publisher_location


def _write_bib(tmp_path: Path, content: str) -> Path:
    bib_path = tmp_path / "library.bib"
    bib_path.write_text(content, encoding="utf-8")
    return bib_path


def test_normalize_publisher_location_updates_fields(tmp_path: Path) -> None:
    bib_content = """@book{entry-one,
  title = {First Book},
  publisher = {Springer, Berlin}
}

@book{entry-two,
  title = {Second Book},
  publisher = {Existing Publisher},
  location = {Existing Location}
}
"""
    bib_path = _write_bib(tmp_path, bib_content)

    report = normalize_publisher_location(bib_path)

    assert report.flagged == ["entry-one"]
    assert report.fixed == ["entry-one"]

    library = bibtexparser.parse_file(str(bib_path))
    entry_one = next(entry for entry in library.entries if entry.key == "entry-one")

    assert entry_one.fields_dict["publisher"].value == "Springer"
    assert entry_one.fields_dict["location"].value == "Berlin"


def test_normalize_publisher_location_dry_run(tmp_path: Path) -> None:
    bib_content = """@book{entry-one,
  title = {Dry Run},
  publisher = {Springer, Berlin}
}
"""
    bib_path = _write_bib(tmp_path, bib_content)
    before = bib_path.read_text(encoding="utf-8")

    report = normalize_publisher_location(bib_path, dry_run=True)

    assert report.flagged == ["entry-one"]
    assert report.fixed == ["entry-one"]
    after = bib_path.read_text(encoding="utf-8")
    assert after == before


def test_normalize_publisher_location_flags_multicomma(tmp_path: Path) -> None:
    bib_content = """@book{entry-one,
  title = {Manual Review},
  publisher = {Springer, Berlin, Germany}
}
"""
    bib_path = _write_bib(tmp_path, bib_content)
    before = bib_path.read_text(encoding="utf-8")

    report = normalize_publisher_location(bib_path)

    assert report.flagged == ["entry-one"]
    assert report.fixed == []
    after = bib_path.read_text(encoding="utf-8")
    assert after == before

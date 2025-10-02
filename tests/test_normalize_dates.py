"""Tests for date normalization helpers."""

from __future__ import annotations

from pathlib import Path

import bibtexparser

from biblib.normalize.dates import rename_year_to_date_fields


def test_rename_year_to_date_updates_entries(tmp_path: Path) -> None:
    """Entries with year but no date should be converted."""
    bib_content = """@book{entry-one,
  title = {First Book},
  author = {Alpha, Author},
  year = {2020}
}

@article{entry-two,
  title = {Second Article},
  date = {2021-05-03}
}
"""
    bib_path = tmp_path / "library.bib"
    bib_path.write_text(bib_content, encoding="utf-8")

    updated_count, updated_keys = rename_year_to_date_fields(bib_path)

    assert updated_count == 1
    assert updated_keys == ["entry-one"]

    library = bibtexparser.parse_file(str(bib_path))
    entry_one = next(entry for entry in library.entries if entry.key == "entry-one")

    assert "date" in entry_one.fields_dict
    assert "year" not in entry_one.fields_dict
    assert entry_one.fields_dict["date"].value == "2020"


def test_rename_year_to_date_dry_run(tmp_path: Path) -> None:
    """Dry-run should report entries without modifying the file."""
    bib_content = """@book{entry-one,
  title = {Dry Run Book},
  year = {1999}
}
"""
    bib_path = tmp_path / "library.bib"
    bib_path.write_text(bib_content, encoding="utf-8")
    before = bib_path.read_text(encoding="utf-8")

    updated_count, updated_keys = rename_year_to_date_fields(bib_path, dry_run=True)

    assert updated_count == 1
    assert updated_keys == ["entry-one"]

    after = bib_path.read_text(encoding="utf-8")
    assert after == before

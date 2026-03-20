"""Tests for LaTeX accent normalization."""

from __future__ import annotations

from pathlib import Path

import bibtexparser

from biblio.normalize.accents import normalize_latex_accents


def _write_bib(tmp_path: Path, content: str) -> Path:
    bib_path = tmp_path / "library.bib"
    bib_path.write_text(content, encoding="utf-8")
    return bib_path


def test_normalize_latex_accents_updates_fields(tmp_path: Path) -> None:
    bib_content = r"""@book{accented,
  author = {Jos\'e Mart{\'i}},
  title = {Fran{\c{c}}ois and G\"odel},
  note = {Br\"{\i}gge and Moli\`ere},
  publisher = {G\ae{}teborg Press}
}

@misc{special,
  title = {D{\"{\i}}r{\'e}},
  keywords = {Kr\'en and Moli\`ere},
  note = {Keep braces {L} around ascii}
}
"""
    bib_path = _write_bib(tmp_path, bib_content)

    report = normalize_latex_accents(bib_path)

    assert report.converted == {
        "accented": ["author", "title", "note", "publisher"],
        "special": ["title", "keywords"],
    }
    assert report.total_fields == 6

    library = bibtexparser.parse_file(str(bib_path))
    accented = next(entry for entry in library.entries if entry.key == "accented")
    special = next(entry for entry in library.entries if entry.key == "special")

    accented_fields = accented.fields_dict
    assert accented_fields["author"].value == "José Martí"
    assert accented_fields["title"].value == "François and Gödel"
    assert accented_fields["note"].value == "Brïgge and Molière"
    assert accented_fields["publisher"].value == "Gæteborg Press"

    special_fields = special.fields_dict
    assert special_fields["title"].value == "Dïré"
    assert special_fields["keywords"].value == "Krén and Molière"
    assert special_fields["note"].value == "Keep braces {L} around ascii"


def test_normalize_latex_accents_preserves_font_commands(tmp_path: Path) -> None:
    """Regression: \\rm, \\bf etc. are font commands, not accents."""
    bib_content = r"""@incollection{font-cmds,
  title = {Pentagon relation for {$\scr M_{0,5}^{\rm cyc}$}},
  note = {Use {\bf bold} and {\it italic} here},
  keywords = {The \r{o}le of accents}
}
"""
    bib_path = _write_bib(tmp_path, bib_content)

    report = normalize_latex_accents(bib_path)

    # Only the braced \r{o} should be converted, not \rm, \bf, \it
    assert report.converted == {"font-cmds": ["keywords"]}

    library = bibtexparser.parse_file(str(bib_path))
    entry = next(e for e in library.entries if e.key == "font-cmds")
    fields = entry.fields_dict
    assert r"\rm cyc" in fields["title"].value
    assert r"\bf bold" in fields["note"].value
    assert r"\it italic" in fields["note"].value
    assert "o\u030a" not in fields["title"].value  # no ring accent on title
    assert "r\u030ale" not in fields["keywords"].value  # \r{o} -> ů, not \role


def test_normalize_latex_accents_dry_run(tmp_path: Path) -> None:
    bib_content = r"""@book{accented,
  author = {Jos\'e},
  title = {Fran{\c{c}}ois}
}
"""
    bib_path = _write_bib(tmp_path, bib_content)
    before = bib_path.read_text(encoding="utf-8")

    report = normalize_latex_accents(bib_path, dry_run=True)

    assert report.converted == {"accented": ["author", "title"]}
    assert report.total_fields == 2
    after = bib_path.read_text(encoding="utf-8")
    assert after == before

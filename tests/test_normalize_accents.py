"""Tests for pure LaTeX text normalization."""

import bibtexparser

from biblio.bibliography import Bibliography, IdentityIndex
from biblio.normalize.accents import normalize_latex_accents


def _bibliography(source: str) -> Bibliography:
    library = bibtexparser.parse_string(source)
    return Bibliography(library.blocks, IdentityIndex(library.entries))


def test_normalizes_accents_special_macros_and_reviewer_spaces() -> None:
    bibliography = _bibliography(
        r"""@book{accented,
  author = {Jos\'e Mart{\'i}},
  title = {Fran{\c{c}}ois and G\"odel},
  publisher = {G\ae{}teborg Press},
  mrreviewer = {Victor\ Mikhailovich}
}
"""
    )

    report = normalize_latex_accents(bibliography)

    assert report.converted == {"accented": ("author", "title", "publisher", "mrreviewer")}
    fields = bibliography.resolve("accented").fields_dict
    assert fields["author"].value == "José Martí"
    assert fields["title"].value == "François and Gödel"
    assert fields["publisher"].value == "Gæteborg Press"
    assert fields["mrreviewer"].value == "Victor Mikhailovich"


def test_preserves_font_commands_math_spacing_and_identity_aliases() -> None:
    bibliography = _bibliography(
        r"""@incollection{font,
  ids = {Ret\'ired},
  title = {Pentagon {$\scr M^{\rm cyc}$}},
  note = {Keep $x\ y$ and {\bf bold}},
  keywords = {The \r{o}le}
}
"""
    )

    report = normalize_latex_accents(bibliography)

    assert report.converted == {"font": ("keywords",)}
    fields = bibliography.resolve("font").fields_dict
    assert fields["ids"].value == r"Ret\'ired"
    assert r"\rm cyc" in fields["title"].value
    assert r"$x\ y$" in fields["note"].value
    bibliography.validate()


def test_preserves_every_identifier_and_identifier_metadata_field_exactly() -> None:
    protected = {
        "doi": r"10.1000/Jos\'e",
        "isbn": r"978-Jos\'e",
        "isbn13": r"978-Jos\'e",
        "eprint": r"Jos\'e.12345",
        "url": r"https://example.test/Jos\'e",
        "mrnumber": r"MR-Jos\'e",
        "zbl": r"ZBL-Jos\'e",
        "zbmath": r"ZBMATH-Jos\'e",
        "jfm": r"JFM-Jos\'e",
        "oclc": r"OCLC-Jos\'e",
        "hdl": r"HDL/Jos\'e",
        "acmdl_doi": r"10.1145/Jos\'e",
        "ids": r"Ret\'ired",
        "eprinttype": r"arX\'iv",
        "archiveprefix": r"arX\'iv",
        "eprintclass": r"math.Jos\'e",
        "primaryclass": r"math.Jos\'e",
    }
    rendered_fields = ",\n".join(f"  {name} = {{{value}}}" for name, value in protected.items())
    bibliography = _bibliography(
        f"@online{{opaque,\n{rendered_fields},\n"
        r"  title = {Jos\'e},"
        "\n"
        r"  mrreviewer = {Victor\ Mikhailovich}"
        "\n}\n"
    )

    report = normalize_latex_accents(bibliography)

    assert report.converted == {"opaque": ("title", "mrreviewer")}
    fields = bibliography.resolve("opaque").fields_dict
    assert {name: str(fields[name].value) for name in protected} == protected
    assert fields["title"].value == "José"
    assert fields["mrreviewer"].value == "Victor Mikhailovich"
    bibliography.validate()


def test_accent_normalization_reports_noop() -> None:
    bibliography = _bibliography("@book{plain, title={Plain}}\n")

    assert normalize_latex_accents(bibliography).changes.changed is False

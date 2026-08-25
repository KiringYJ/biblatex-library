"""Tests for deterministic whitespace cleanup in BibLaTeX name lists."""

import bibtexparser

from biblio.bibliography import Bibliography, IdentityIndex
from biblio.normalize.names import normalize_name_spacing


def _bibliography(source: str) -> Bibliography:
    library = bibtexparser.parse_string(source)
    return Bibliography(library.blocks, IdentityIndex(library.entries))


def test_name_fields_remove_horizontal_space_before_commas() -> None:
    bibliography = _bibliography(
        "@article{one,author={Macrì , Emanuele and Doe, Jane},"
        "editor={Smith  , John},note={Keep this , punctuation}}\n"
    )

    changes = normalize_name_spacing(bibliography)

    fields = bibliography.resolve("one").fields_dict
    assert changes.changed_keys == ("one",)
    assert fields["author"].value == "Macrì, Emanuele and Doe, Jane"
    assert fields["editor"].value == "Smith, John"
    assert fields["note"].value == "Keep this , punctuation"


def test_name_spacing_normalization_is_idempotent() -> None:
    bibliography = _bibliography("@article{one,author={Doe, Jane}}\n")

    assert normalize_name_spacing(bibliography).changed is False

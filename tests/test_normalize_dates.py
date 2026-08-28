"""Tests for pure date normalization."""

import bibtexparser
import pytest

from biblio.bibliography import Bibliography, IdentityIndex
from biblio.normalize.dates import rename_year_to_date_fields


def _bibliography(source: str) -> Bibliography:
    library = bibtexparser.parse_string(source)
    return Bibliography(library.blocks, IdentityIndex(library.entries))


def test_rename_year_to_date_updates_entries_in_place() -> None:
    bibliography = _bibliography(
        "@book{one, year={2020}}\n@article{two, date={2021}, year={2020}}\n"
    )

    changes = rename_year_to_date_fields(bibliography)

    assert changes.changed_keys == ("one",)
    assert [(delta.field, delta.before, delta.after) for delta in changes.field_deltas] == [
        ("year", "2020", None),
        ("date", None, "2020"),
    ]
    assert "year" not in bibliography.resolve("one").fields_dict
    assert bibliography.resolve("one").fields_dict["date"].value == "2020"
    assert bibliography.resolve("two").fields_dict["year"].value == "2020"


def test_rename_year_to_date_reports_explicit_noop() -> None:
    bibliography = _bibliography("@article{one, date={2021}}\n")

    assert rename_year_to_date_fields(bibliography).changed is False


@pytest.mark.parametrize(
    "fields",
    [
        "year={2020},MONTH={12}",
        "YEAR={2020},DATE={2021}",
        "year={forthcoming}",
        "year={２０２０}",
        "year={20}",
        "year={ 2020 }",
        "year={2020/2021}",
    ],
)
def test_preserves_year_outside_exact_year_only_contract(fields: str) -> None:
    bibliography = _bibliography(f"@book{{one,{fields}}}")
    before = tuple((field.key, field.value) for field in bibliography.resolve("one").fields)

    assert not rename_year_to_date_fields(bibliography).changed
    assert tuple((field.key, field.value) for field in bibliography.resolve("one").fields) == before


def test_renames_uppercase_year_in_place() -> None:
    bibliography = _bibliography("@book{one,title={Title},YEAR={2020},author={Doe}}")
    assert rename_year_to_date_fields(bibliography).changed_keys == ("one",)
    assert [field.key for field in bibliography.resolve("one").fields] == [
        "title",
        "date",
        "author",
    ]

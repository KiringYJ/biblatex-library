"""Regression tests for plain top-level name separator spacing."""

import bibtexparser
import pytest

from biblio.bibliography import Bibliography, IdentityIndex
from biblio.normalize.names import normalize_name_spacing, normalize_name_value


@pytest.mark.parametrize(
    "before, after",
    [
        ("Doe , Jane", "Doe, Jane"),
        ("Macrì , Emanuele and Smith\t , John", "Macrì, Emanuele and Smith, John"),
        ("Doe , Jr. , Jane", "Doe, Jr., Jane"),
        ("{Research , Development}", "{Research , Development}"),
        ("{Research , Development} and Doe , Jane", "{Research , Development} and Doe, Jane"),
        ("{van Doe} , Jane", "{van Doe}, Jane"),
        ("Doe, Jane", "Doe, Jane"),
    ],
)
def test_plain_top_level_separator_spacing(before: str, after: str) -> None:
    assert normalize_name_value(before) == after
    assert normalize_name_value(after) == after


@pytest.mark.parametrize(
    "value",
    [
        r"Doe\ , John",
        r"Doe\ , John and Smith , Jane",
        r"Doe\, , John",
        r"family=\"Doe , Family\", given=Jane",
        'family="Doe , Family", given=Jane',
        '"Doe , Family", Jane',
        r"Doe , Jane and \unknown{Smith , John}",
        r"Doe , Jane and \textbf{Smith , John}",
        r"\verb|Doe , Jane|",
        "Doe , Jane % comment",
        "Doe , Jane $x$",
        r"Doe , Jane \(x\)",
        "Doe , Jane and {Research",
        "Doe , Jane}",
        "Doe , Jane \\",
        "Doe , Jane #1",
        "Doe , Jane & Co.",
        "Doe , Jane~Junior",
    ],
)
def test_opaque_or_malformed_name_syntax_is_preserved(value: str) -> None:
    assert normalize_name_value(value) == value


def test_name_fields_only_and_exact_change_report() -> None:
    library = bibtexparser.parse_string(
        "@article{one,AUTHOR={Doe , Jane},editor={Smith  , John},note={Keep this , punctuation}}"
    )
    bibliography = Bibliography(library.blocks, IdentityIndex(library.entries))
    report = normalize_name_spacing(bibliography)
    assert report.changed_keys == ("one",)
    assert [(delta.field, delta.before, delta.after) for delta in report.field_deltas] == [
        ("AUTHOR", "Doe , Jane", "Doe, Jane"),
        ("editor", "Smith  , John", "Smith, John"),
    ]
    assert bibliography.resolve("one").fields_dict["note"].value == "Keep this , punctuation"
    assert not normalize_name_spacing(bibliography).changed


def test_deeply_nested_literal_name_does_not_recurse() -> None:
    value = "{" * 2000 + "Research , Development" + "}" * 2000 + " and Doe , Jane"
    assert normalize_name_value(value) == value.replace("Doe , Jane", "Doe, Jane")


@pytest.mark.parametrize("control", ["\x00", "\x0b", "\x0c", "\x7f"])
def test_raw_control_characters_preserve_the_name_field(control: str) -> None:
    value = "Doe , Jane" + control
    assert normalize_name_value(value) == value

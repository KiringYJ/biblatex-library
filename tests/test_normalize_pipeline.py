"""Tests for the single-load normalization dispatcher."""

import bibtexparser
import pytest

from biblio.bibliography import Bibliography, IdentityIndex
from biblio.normalize.pipeline import NORMALIZATION_ACTIONS, normalize_bibliography


def _bibliography(source: str) -> Bibliography:
    library = bibtexparser.parse_string(source)
    return Bibliography(library.blocks, IdentityIndex(library.entries))


def test_all_actions_share_one_aggregate_and_preserve_physical_order() -> None:
    bibliography = _bibliography(
        r"""@comment{before}
@misc{first,
  year = {2020},
  archiveprefix = {arXiv},
  primaryclass = {math.AG},
  eprint = {2001.00001},
  url = {https://arxiv.org/abs/2001.00001},
  title = {Jos\'e}
}
@comment{between}
@book{second,
  publisher = {Springer, Berlin},
  isbn = {0-387-97926-3}
}
"""
    )
    original_nonentry_blocks = tuple(
        block for block in bibliography.blocks if not hasattr(block, "key")
    )

    result = normalize_bibliography(bibliography, "all")

    assert result.actions == NORMALIZATION_ACTIONS
    assert result.changes.changed
    assert result.changes.changed_keys == ("first", "second")
    assert [entry.key for entry in bibliography] == ["first", "second"]
    assert (
        tuple(block for block in bibliography.blocks if not hasattr(block, "key"))
        == original_nonentry_blocks
    )
    first = bibliography.resolve("first")
    assert first.entry_type == "online"
    assert first.fields_dict["date"].value == "2020"
    assert first.fields_dict["title"].value == "José"
    assert "url" not in first.fields_dict
    second = bibliography.resolve("second")
    assert second.fields_dict["publisher"].value == "Springer, Berlin"
    assert "location" not in second.fields_dict
    assert second.fields_dict["isbn"].value == "9780387979267"


def test_second_all_run_is_an_explicit_noop() -> None:
    bibliography = _bibliography("@article{one, date={2020}, title={Plain}}\n")

    result = normalize_bibliography(bibliography, "all")

    assert result.actions == NORMALIZATION_ACTIONS
    assert result.changes.changed is False
    assert result.commit is None


def test_single_action_does_not_apply_other_normalizers() -> None:
    bibliography = _bibliography("@book{one, year={2020}, isbn={0-387-97926-3}}\n")

    result = normalize_bibliography(bibliography, "year-to-date")

    assert result.actions == ("year-to-date",)
    assert bibliography.resolve("one").fields_dict["isbn"].value == "0-387-97926-3"


def test_unknown_action_fails_without_mutation() -> None:
    bibliography = _bibliography("@book{one, year={2020}}\n")

    with pytest.raises(ValueError, match="unknown normalization action"):
        normalize_bibliography(bibliography, "alphabetize")

    assert "year" in bibliography.resolve("one").fields_dict


def test_no_change_manual_review_and_invalid_isbn_diagnostics_survive() -> None:
    bibliography = _bibliography(
        "@book{date, year={forthcoming}}\n@book{isbn, isbn={not-an-isbn}}\n"
    )

    result = normalize_bibliography(bibliography, "all")

    assert not result.changes.changed
    assert result.diagnostics == (
        "year-to-date:manual-review:date",
        "isbn:invalid:isbn:not-an-isbn",
    )


def test_eprint_conflicts_are_reported_without_overwriting() -> None:
    bibliography = _bibliography(
        "@misc{type,archiveprefix={arXiv},eprinttype={HAL}}\n"
        "@misc{class,eprinttype={arxiv},primaryclass={math.AG},eprintclass={cs.LO}}\n"
    )

    result = normalize_bibliography(bibliography, "all")

    assert result.changes.changed is False
    assert result.diagnostics == (
        "eprint-fields:manual-review:type:archiveprefix->eprinttype:conflict",
        "eprint-fields:manual-review:class:primaryclass->eprintclass:conflict",
    )


@pytest.mark.parametrize("action", NORMALIZATION_ACTIONS)
def test_retained_actions_are_individually_selectable(action: str) -> None:
    bibliography = _bibliography("@book{one,title={Plain}}")

    result = normalize_bibliography(bibliography, action)

    assert result.actions == (action,)
    assert not result.changes.changed

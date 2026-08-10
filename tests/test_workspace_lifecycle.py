"""Tests for lifecycle transformations over the three-artifact workspace."""

import hashlib
from copy import deepcopy

import bibtexparser
import pytest
from bibtexparser.model import Entry

from biblio.bibliography import Bibliography, IdentityIndex
from biblio.identifier_collection import IdentifierRecord, KeyHistory
from biblio.lifecycle import promote_in_workspace, remove_from_workspace
from biblio.workspace import WorkspaceAggregate


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:8]


def _entry(source: str) -> Entry:
    library = bibtexparser.parse_string(source)
    assert not library.failed_blocks
    return library.entries[0]


def _bibliography(source: str) -> Bibliography:
    library = bibtexparser.parse_string(source)
    assert not library.failed_blocks
    return Bibliography(library.blocks, IdentityIndex(library.entries))


def _workspace(*, include_collision: bool = False) -> WorkspaceAggregate:
    arxiv = "2101.00001v2"
    derived_doi = "10.48550/arXiv.2101.00001v2"
    old_key = f"doe-2021-{_hash(arxiv)}"
    other_url = "https://example.test/other"
    other_key = f"other-2020-{_hash(other_url)}"
    bibliography = _bibliography(
        f"@online{{{old_key},author={{Doe, Jane}},title={{Preprint}},date={{2021}},"
        f"eprint={{{arxiv}}},eprinttype={{arxiv}},doi={{{derived_doi}}}}}\n"
        f"@book{{{other_key},title={{Other}},url={{{other_url}}}}}\n"
    )
    other_identifiers = {"url": other_url}
    if include_collision:
        other_identifiers["doi"] = "10.1000/PUBLISHED"
    aggregate = WorkspaceAggregate(
        bibliography,
        {
            old_key: IdentifierRecord(
                "arxiv",
                {
                    "arxiv": arxiv,
                    "doi": derived_doi,
                    "mrnumber": "JSON-ONLY",
                },
            ),
            other_key: IdentifierRecord("url", other_identifiers),
        },
        (old_key, other_key),
    )
    aggregate.validate()
    return aggregate


def _published(doi: str = "10.1000/published", *, date: str = "2024") -> Entry:
    return _entry(
        f"@article{{payload,author={{Doe, Jane}},title={{Published}},date={{{date}}},"
        f"journaltitle={{Journal}},doi={{{doi}}},isbn={{9780306406157}}}}\n"
    )


def test_promote_merges_complete_inventory_history_aliases_and_order() -> None:
    aggregate = _workspace()
    old_key = aggregate.add_order[0]
    expected_new = f"doe-2024-{_hash('10.1000/published')}"

    result = promote_in_workspace(
        aggregate,
        old_key,
        _published(),
        "10.1000/published",
        stripped_doi_query=True,
    )

    assert result.new_key == expected_new
    assert result.aliases == (old_key,)
    assert result.stripped_doi_query
    assert aggregate.add_order == (expected_new, aggregate.add_order[1])
    assert tuple(entry.key for entry in aggregate.bibliography) == aggregate.add_order
    assert aggregate.bibliography.resolve(old_key).key == expected_new
    record = aggregate.identifiers[expected_new]
    assert record.main_identifier == "doi"
    assert record.identifiers == {
        "arxiv": "2101.00001v2",
        "doi": "10.1000/published",
        "mrnumber": "JSON-ONLY",
        "isbn13": "9780306406157",
    }
    assert record.identifier_alternates == {"doi": ("10.48550/arXiv.2101.00001v2",)}
    assert record.key_history == (
        KeyHistory(old_key, "arxiv", "2101.00001v2"),
        KeyHistory(expected_new, "doi", "10.1000/published"),
    )
    aggregate.validate()


def test_repeated_promotion_history_order_matches_ids_alias_order() -> None:
    aggregate = _workspace()
    original_key = aggregate.add_order[0]
    first = promote_in_workspace(aggregate, original_key, _published(), "10.1000/published")

    second = promote_in_workspace(
        aggregate,
        original_key,
        _published("10.2000/final", date="2025"),
        "10.2000/final",
    )

    assert second.aliases == (first.new_key, original_key)
    assert aggregate.bibliography.aliases_for(second.new_key) == second.aliases
    record = aggregate.identifiers[second.new_key]
    assert tuple(item.key for item in record.key_history) == (
        first.new_key,
        original_key,
        second.new_key,
    )
    assert tuple(item.identifier for item in record.key_history) == (
        "10.1000/published",
        "2101.00001v2",
        "10.2000/final",
    )
    assert record.identifier_alternates["doi"] == (
        "10.1000/published",
        "10.48550/arXiv.2101.00001v2",
    )
    aggregate.validate()


def test_remove_by_alias_deletes_all_three_artifacts() -> None:
    aggregate = _workspace()
    old_key = aggregate.add_order[0]
    promoted = promote_in_workspace(aggregate, old_key, _published(), "10.1000/published")
    remaining_key = aggregate.add_order[1]

    result = remove_from_workspace(aggregate, old_key)

    assert result.canonical_key == promoted.new_key
    assert result.aliases == (old_key,)
    assert aggregate.add_order == (remaining_key,)
    assert tuple(aggregate.identifiers) == (remaining_key,)
    assert tuple(entry.key for entry in aggregate.bibliography) == (remaining_key,)
    aggregate.validate()


def test_promotion_collision_leaves_workspace_unchanged() -> None:
    aggregate = _workspace(include_collision=True)
    before = deepcopy(aggregate)
    old_key = aggregate.add_order[0]

    with pytest.raises(ValueError, match="collides with record"):
        promote_in_workspace(
            aggregate,
            old_key,
            _published(),
            "10.1000/published",
        )

    assert aggregate.add_order == before.add_order
    assert aggregate.identifiers == before.identifiers
    assert tuple(entry.key for entry in aggregate.bibliography) == tuple(
        entry.key for entry in before.bibliography
    )
    assert aggregate.bibliography.resolve(old_key).fields_dict["doi"].value == (
        "10.48550/arXiv.2101.00001v2"
    )


def test_invalid_payload_leaves_workspace_unchanged() -> None:
    aggregate = _workspace()
    before = deepcopy(aggregate)
    old_key = aggregate.add_order[0]

    with pytest.raises(ValueError, match="must equal the command-supplied canonical DOI"):
        promote_in_workspace(
            aggregate,
            old_key,
            _published("10.9999/wrong"),
            "10.1000/published",
        )

    assert aggregate.add_order == before.add_order
    assert aggregate.identifiers == before.identifiers
    assert aggregate.bibliography.resolve(old_key).fields_dict["doi"].value == (
        "10.48550/arXiv.2101.00001v2"
    )

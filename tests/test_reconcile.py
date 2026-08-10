"""Tests for monotonic bibliography-to-inventory reconciliation."""

import hashlib
from copy import deepcopy

import bibtexparser
import pytest

from biblio.bibliography import Bibliography, IdentityIndex
from biblio.identifier_collection import IdentifierRecord, KeyHistory
from biblio.reconcile import reconcile_identifier_inventory
from biblio.workspace import WorkspaceAggregate


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:8]


def _bibliography(source: str) -> Bibliography:
    library = bibtexparser.parse_string(source)
    assert not library.failed_blocks
    return Bibliography(library.blocks, IdentityIndex(library.entries))


def test_adds_missing_primary_and_non_equivalent_alternate_monotonically() -> None:
    doi = "10.1000/work"
    old_url = "https://example.test/old"
    new_url = "https://example.test/new"
    key = f"doe-2024-{_hash(doi)}"
    history = (KeyHistory(key, "doi", doi),)
    bibliography = _bibliography(
        f"@article{{{key},doi={{{doi}}},url={{{new_url}}},mrnumber={{MR123}}}}\n"
    )
    aggregate = WorkspaceAggregate(
        bibliography,
        {
            key: IdentifierRecord(
                "doi",
                {"doi": doi, "url": old_url},
                key_history=history,
            )
        },
        (key,),
    )
    bibliography_before = aggregate.bibliography
    order_before = aggregate.add_order

    result = reconcile_identifier_inventory(aggregate)

    assert [(item.kind, item.exact_value, item.added_as) for item in result.additions] == [
        ("url", new_url, "alternate"),
        ("mrnumber", "MR123", "primary"),
    ]
    assert result.changes.changed_keys == (key,)
    record = aggregate.identifiers[key]
    assert record.identifiers == {"doi": doi, "url": old_url, "mrnumber": "MR123"}
    assert record.identifier_alternates == {"url": (new_url,)}
    assert record.main_identifier == "doi"
    assert record.key_history == history
    assert aggregate.bibliography is bibliography_before
    assert aggregate.add_order is order_before
    aggregate.validate()

    identifiers_after_first_pass = aggregate.identifiers
    repeated = reconcile_identifier_inventory(aggregate)
    assert repeated.additions == ()
    assert not repeated.changes.changed
    assert aggregate.identifiers is identifiers_after_first_pass


def test_equivalent_projection_is_noop_and_preserves_exact_inventory() -> None:
    doi = "10.1000/work"
    exact_isbn10 = "0-387-97926-3"
    key = f"doe-2024-{_hash(doi)}"
    aggregate = WorkspaceAggregate(
        _bibliography(f"@book{{{key},doi={{{doi}}},isbn={{978-0-387-97926-7}}}}\n"),
        {key: IdentifierRecord("doi", {"doi": doi, "isbn13": exact_isbn10})},
        (key,),
    )
    identifiers_before = aggregate.identifiers

    result = reconcile_identifier_inventory(aggregate)

    assert result.additions == ()
    assert not result.changes.changed
    assert aggregate.identifiers is identifiers_before
    assert aggregate.identifiers[key].identifiers["isbn13"] == exact_isbn10


def test_collision_aborts_without_mutating_input() -> None:
    first_doi = "10.1000/first"
    second_doi = "10.1000/second"
    shared_url = "https://example.test/shared"
    first_key = f"first-2024-{_hash(first_doi)}"
    second_key = f"second-2024-{_hash(second_doi)}"
    aggregate = WorkspaceAggregate(
        _bibliography(
            f"@article{{{first_key},doi={{{first_doi}}},url={{{shared_url}}}}}\n"
            f"@article{{{second_key},doi={{{second_doi}}}}}\n"
        ),
        {
            first_key: IdentifierRecord("doi", {"doi": first_doi}),
            second_key: IdentifierRecord("doi", {"doi": second_doi, "url": shared_url}),
        },
        (first_key, second_key),
    )
    before = deepcopy(aggregate.identifiers)

    with pytest.raises(ValueError, match="collides with record"):
        reconcile_identifier_inventory(aggregate)

    assert aggregate.identifiers == before


def test_unrelated_workspace_issue_aborts_without_mutating_input() -> None:
    doi = "10.1000/work"
    key = f"doe-2024-{_hash(doi)}"
    aggregate = WorkspaceAggregate(
        _bibliography(f"@article{{{key},doi={{{doi}}},url={{https://example.test}}}}\n"),
        {key: IdentifierRecord("doi", {"doi": doi})},
        ("wrong-order-key",),
    )
    before = deepcopy(aggregate.identifiers)

    with pytest.raises(ValueError, match="canonical keysets differ"):
        reconcile_identifier_inventory(aggregate)

    assert aggregate.identifiers == before

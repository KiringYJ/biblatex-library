"""Tests for cross-artifact workspace validation."""

import hashlib
from copy import deepcopy

import bibtexparser
import pytest

from biblio.bibliography import Bibliography, IdentityIndex
from biblio.identifier_collection import IdentifierRecord, KeyHistory
from biblio.workspace import WorkspaceAggregate


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:8]


def _bibliography(source: str) -> Bibliography:
    library = bibtexparser.parse_string(source)
    assert not library.failed_blocks
    return Bibliography(library.blocks, IdentityIndex(library.entries))


def test_validates_json_only_identifiers_and_complete_alias_history() -> None:
    arxiv = "2101.00001v2"
    doi = "10.1000/published"
    old_key = f"doe-2021-{_hash(arxiv)}"
    key = f"doe-2022-{_hash(doi)}"
    bibliography = _bibliography(
        f"@article{{{key},doi={{{doi}}},eprint={{{arxiv}}},"
        f"eprinttype={{arxiv}},ids={{{old_key}}}}}\n"
    )
    aggregate = WorkspaceAggregate(
        bibliography,
        {
            key: IdentifierRecord(
                "doi",
                {"doi": doi, "arxiv": arxiv, "mrnumber": "JSON-ONLY"},
                {"doi": ("10.48550/arXiv.2101.00001v2",)},
                (
                    KeyHistory(old_key, "arxiv", arxiv),
                    KeyHistory(key, "doi", doi),
                ),
            )
        },
        (key,),
    )

    aggregate.validate()
    copied = deepcopy(aggregate)
    copied.validate()
    assert copied is not aggregate
    assert copied.bibliography is not aggregate.bibliography


@pytest.mark.parametrize(
    ("record", "aliases", "message"),
    [
        (
            IdentifierRecord("unknown", {"unknown": "value"}),
            "",
            "unknown identifier kind 'unknown'",
        ),
        (
            IdentifierRecord("doi", {"doi": "10.1000/x"}, {"doi": ("10.1000/x",)}),
            "",
            "duplicates primary exact value",
        ),
        (
            IdentifierRecord("doi", {"doi": "10.1000/x"}),
            "old-key",
            "aliases require key_history",
        ),
    ],
)
def test_rejects_unknown_duplicate_and_unproven_identifiers(
    record: IdentifierRecord, aliases: str, message: str
) -> None:
    key = f"one-{_hash(record.identifiers[record.main_identifier])}"
    ids = f",ids={{{aliases}}}" if aliases else ""
    aggregate = WorkspaceAggregate(
        _bibliography(f"@article{{{key}{ids}}}\n"),
        {key: record},
        (key,),
    )

    with pytest.raises(ValueError, match=message):
        aggregate.validate()


def test_rejects_keyset_order_projection_and_history_mismatches() -> None:
    doi = "10.1000/x"
    key = f"one-{_hash(doi)}"
    old = f"old-{_hash('2101.1')}"
    aggregate = WorkspaceAggregate(
        _bibliography(f"@article{{{key},doi={{10.1000/other}},ids={{{old}}}}}\n"),
        {
            key: IdentifierRecord(
                "doi",
                {"doi": doi, "arxiv": "2101.1"},
                key_history=(KeyHistory(key, "doi", doi),),
            ),
            "extra": IdentifierRecord("url", {"url": "https://example.test"}),
        },
        ("extra", key),
    )

    with pytest.raises(ValueError) as error:
        aggregate.validate()

    message = str(error.value)
    assert "canonical keysets differ" in message
    assert "physical bibliography order differs" in message
    assert "key_history keys" in message
    assert "bibliography identifier 'doi'" in message


def test_rejects_normalized_identifier_collisions_within_and_across_records() -> None:
    first_doi = "10.1000/ONE"
    second_doi = "10.1000/TWO"
    first_key = f"first-{_hash(first_doi)}"
    second_key = f"second-{_hash(second_doi)}"
    aggregate = WorkspaceAggregate(
        _bibliography(f"@article{{{first_key}}}\n@article{{{second_key}}}\n"),
        {
            first_key: IdentifierRecord(
                "doi",
                {"doi": first_doi, "isbn13": "978-0-306-40615-7"},
                {"doi": ("DOI:10.1000/one",)},
            ),
            second_key: IdentifierRecord(
                "doi",
                {"doi": second_doi, "isbn13": "9780306406157"},
            ),
        },
        (first_key, second_key),
    )

    with pytest.raises(ValueError) as error:
        aggregate.validate()

    message = str(error.value)
    assert "equivalent duplicate 'doi'" in message
    assert "identifier 'isbn13'" in message
    assert "collides with record" in message


def test_spaced_arxiv_marker_is_compared_against_exact_inventory() -> None:
    exact = "2101.00001"
    key = f"one-{_hash(exact)}"
    aggregate = WorkspaceAggregate(
        _bibliography(f"@online{{{key},eprint={{9999.99999}},eprinttype={{ arXiv }}}}\n"),
        {key: IdentifierRecord("arxiv", {"arxiv": exact})},
        (key,),
    )

    with pytest.raises(ValueError, match="bibliography identifier 'arxiv'"):
        aggregate.validate()


def test_isbn13_projection_preserves_isbn10_hash_provenance() -> None:
    exact_isbn10 = "0-387-97926-3"
    key = f"one-{_hash(exact_isbn10)}"
    aggregate = WorkspaceAggregate(
        _bibliography(f"@book{{{key},isbn={{978-0-387-97926-7}}}}\n"),
        {key: IdentifierRecord("isbn13", {"isbn13": exact_isbn10})},
        (key,),
    )

    aggregate.validate()
    assert aggregate.identifiers[key].identifiers["isbn13"] == exact_isbn10


@pytest.mark.parametrize(
    "record",
    [
        IdentifierRecord("url", {"url": ""}),
        IdentifierRecord("", {"url": "https://example.test"}),
        IdentifierRecord(
            "url",
            {"url": "https://example.test"},
            {"url": ("   ",)},
        ),
    ],
)
def test_rejects_empty_primary_main_and_alternate_identifiers(record: IdentifierRecord) -> None:
    main_value = record.identifiers.get(record.main_identifier, "https://example.test")
    key = f"one-{_hash(main_value)}"
    aggregate = WorkspaceAggregate(
        _bibliography(f"@article{{{key}}}\n"),
        {key: record},
        (key,),
    )

    with pytest.raises(ValueError):
        aggregate.validate()


def test_rejects_empty_key_history_identifier() -> None:
    url = "https://example.test"
    key = f"one-{_hash(url)}"
    alias = f"old-{_hash(' ')}"
    aggregate = WorkspaceAggregate(
        _bibliography(f"@article{{{key},ids={{{alias}}}}}\n"),
        {
            key: IdentifierRecord(
                "url",
                {"url": url},
                key_history=(
                    KeyHistory(alias, "url", " "),
                    KeyHistory(key, "url", url),
                ),
            )
        },
        (key,),
    )

    with pytest.raises(ValueError, match="must not be empty"):
        aggregate.validate()

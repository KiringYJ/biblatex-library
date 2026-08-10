"""Tests for identifier inventory and addition-order domain codecs."""

import hashlib
import json
from pathlib import Path

import bibtexparser
import pytest
from bibtexparser.model import Entry

from biblio.identifier_collection import (
    IdentifierRecord,
    KeyHistory,
    identifier_equality_token,
    identifiers_from_entry,
    parse_add_order,
    parse_identifier_collection,
    serialize_add_order,
    serialize_identifier_collection,
)


def _entry(source: str) -> Entry:
    library = bibtexparser.parse_string(source)
    assert not library.failed_blocks
    return library.entries[0]


def test_flat_legacy_collection_round_trips_without_optional_fields() -> None:
    source = b'{"one":{"main_identifier":"doi","identifiers":{"doi":"10.1000/ABC"}}}'

    collection = parse_identifier_collection(source)

    assert collection == {
        "one": IdentifierRecord("doi", {"doi": "10.1000/ABC"}),
    }
    assert json.loads(serialize_identifier_collection(collection)) == json.loads(source)


def test_current_flat_legacy_fixture_remains_readable_and_writable() -> None:
    source = Path("tests/fixtures/legacy-workspace/identifier_collection.json").read_bytes()

    collection = parse_identifier_collection(source)

    assert len(collection) == 11
    assert parse_identifier_collection(serialize_identifier_collection(collection)) == collection


def test_optional_alternates_and_history_preserve_exact_values() -> None:
    source = b"""{
      "new-00000000": {
        "main_identifier": "doi",
        "identifiers": {"doi": " HTTPS://DOI.ORG/10.1000/NEW ", "arxiv": "2101.00001v2"},
        "identifier_alternates": {"doi": ["10.48550/arXiv.2101.00001v2"]},
        "key_history": [
          {"key": "old-11111111", "main_identifier": "arxiv", "identifier": "2101.00001v2"},
          {"key": "new-00000000", "main_identifier": "doi",
           "identifier": " HTTPS://DOI.ORG/10.1000/NEW "}
        ]
      }
    }"""

    collection = parse_identifier_collection(source)
    record = collection["new-00000000"]

    assert record.identifier_alternates == {"doi": ("10.48550/arXiv.2101.00001v2",)}
    assert record.key_history == (
        KeyHistory("old-11111111", "arxiv", "2101.00001v2"),
        KeyHistory("new-00000000", "doi", " HTTPS://DOI.ORG/10.1000/NEW "),
    )
    assert parse_identifier_collection(serialize_identifier_collection(collection)) == collection


@pytest.mark.parametrize(
    ("kind", "left", "right"),
    [
        ("doi", "HTTPS://DOI.ORG/10.1000/ABC", "10.1000/abc"),
        ("isbn13", "978-0-306-40615-7", "9780306406157"),
        ("arxiv", "arXiv:2101.00001V2", "2101.00001v2"),
        ("mrnumber", "MR0001234", "0001234"),
        ("zbl", " ZBL 1 ", "zbl 1"),
        ("zbmath", " 00001234 ", "00001234"),
        ("jfm", " JFM 42.1 ", "jfm 42.1"),
        ("oclc", " OCN123 ", "ocn123"),
        ("hdl", " 20.500/Case ", "20.500/Case"),
        ("url", " https://example.test/A ", "https://example.test/A"),
        ("acmdl_doi", "DOI:10.1145/ABC", "10.1145/abc"),
    ],
)
def test_all_eleven_identifier_equality_rules(kind: str, left: str, right: str) -> None:
    assert identifier_equality_token(kind, left) == identifier_equality_token(kind, right)


def test_extracts_all_supported_identifiers_and_keeps_acm_url_as_url() -> None:
    entry = _entry(
        """@article{one,
        doi={10.1000/PUBLISHER}, isbn={978-0-306-40615-7},
        eprint={2101.00001v2}, eprinttype={arxiv}, mrnumber={MR0001234},
        zbl={1234.5}, zbmath={00001234}, jfm={JFM 42.1}, oclc={ocn123},
        hdl={20.500/Case}, acmdl_doi={10.1145/ABC},
        url={https://dl.acm.org/doi/10.1145/abc}}
        """
    )

    assert identifiers_from_entry(entry) == {
        "doi": "10.1000/PUBLISHER",
        "isbn13": "978-0-306-40615-7",
        "arxiv": "2101.00001v2",
        "url": "https://dl.acm.org/doi/10.1145/abc",
        "mrnumber": "MR0001234",
        "zbl": "1234.5",
        "zbmath": "00001234",
        "jfm": "JFM 42.1",
        "oclc": "ocn123",
        "hdl": "20.500/Case",
        "acmdl_doi": "10.1145/ABC",
    }


def test_spaced_arxiv_marker_is_projected_as_arxiv() -> None:
    entry = _entry(
        "@online{one,eprint={2101.00001v2},eprinttype={ arXiv },doi={10.48550/arXiv.2101.00001v2}}"
    )

    assert identifiers_from_entry(entry)["arxiv"] == "2101.00001v2"


def test_valid_isbn10_and_isbn13_are_equal_without_rewriting_exact_values() -> None:
    isbn10 = "0-387-97926-3"
    isbn13 = "978-0-387-97926-7"

    assert identifier_equality_token("isbn13", isbn10) == identifier_equality_token(
        "isbn13", isbn13
    )
    record = IdentifierRecord("isbn13", {"isbn13": isbn10})
    assert record.identifiers["isbn13"] == isbn10


def test_order_codec_is_deterministic_and_rejects_duplicates() -> None:
    assert parse_add_order(b'["first", "second"]') == ("first", "second")
    assert serialize_add_order(("first", "second")) == b'[\n  "first",\n  "second"\n]\n'

    with pytest.raises(ValueError, match="duplicate add-order key 'first'"):
        parse_add_order(b'["first", "first"]')


def test_exact_hash_uses_unmodified_utf8_value() -> None:
    exact = " HTTPS://DOI.ORG/10.1000/ABC "
    suffix = hashlib.sha256(exact.encode()).hexdigest()[:8]
    collection = parse_identifier_collection(
        json.dumps(
            {
                f"one-{suffix}": {
                    "main_identifier": "doi",
                    "identifiers": {"doi": exact},
                }
            }
        ).encode()
    )

    assert collection[f"one-{suffix}"].identifiers["doi"] == exact

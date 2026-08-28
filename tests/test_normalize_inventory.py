"""JSON redundancy cleanup preserves independent identifiers and key provenance."""

import bibtexparser
import pytest

from biblio.bibliography import Bibliography, IdentityIndex
from biblio.identifier_collection import IdentifierRecord, KeyHistory
from biblio.identifiers import hash_exact_legacy_identifier
from biblio.normalize.inventory import normalize_identifier_inventory
from biblio.workspace import WorkspaceAggregate


def _workspace(record: IdentifierRecord, *, alias: str | None = None) -> WorkspaceAggregate:
    key = "one-" + hash_exact_legacy_identifier(record.identifiers[record.main_identifier])
    ids = f",ids={{{alias}}}" if alias is not None else ""
    library = bibtexparser.parse_string(f"@online{{{key},title={{Work}}{ids}}}")
    bibliography = Bibliography(library.blocks, IdentityIndex(library.entries))
    aggregate = WorkspaceAggregate(bibliography, {key: record}, (key,))
    aggregate.validate()
    return aggregate


@pytest.mark.parametrize(
    "identifiers, expected",
    [
        (
            {"doi": "10.48550/arxiv.2509.01002", "url": "https://arxiv.org/abs/2509.01002"},
            {},
        ),
        (
            {"doi": "10.1000/published", "url": "https://doi.org/10.1000/PUBLISHED"},
            {"doi": "10.1000/published"},
        ),
        (
            {"doi": "10.48550/arxiv.2509.01002v2", "url": "https://arxiv.org/abs/2509.01002v2"},
            {"doi": "10.48550/arxiv.2509.01002v2", "url": "https://arxiv.org/abs/2509.01002v2"},
        ),
        (
            {"doi": "10.48550/arxiv.2509.01002", "url": "https://arxiv.org/pdf/2509.01002"},
            {"url": "https://arxiv.org/pdf/2509.01002"},
        ),
        (
            {"doi": "10.48550/arxiv.2509.01002", "url": "https://example.test/paper"},
            {"url": "https://example.test/paper"},
        ),
        (
            {"url": "https://doi.org/10.48550/arxiv.2509.01002"},
            {},
        ),
        (
            {"url": "https://doi.org/10.48550/arxiv.2509.01002?download=1"},
            {"url": "https://doi.org/10.48550/arxiv.2509.01002?download=1"},
        ),
    ],
)
def test_json_only_cleanup_uses_the_same_bounded_equivalence_rules(
    identifiers: dict[str, str], expected: dict[str, str]
) -> None:
    record = IdentifierRecord("arxiv", {"arxiv": "2509.01002", **identifiers})
    aggregate = _workspace(record)

    normalize_identifier_inventory(
        aggregate.bibliography, aggregate.identifiers, remove_urls=True, remove_arxiv_dois=True
    )

    assert record.identifiers == {"arxiv": "2509.01002", **expected}
    aggregate.validate()
    assert not normalize_identifier_inventory(
        aggregate.bibliography, aggregate.identifiers, remove_urls=True, remove_arxiv_dois=True
    ).changes.changed


@pytest.mark.parametrize("kind", ["doi", "url"])
def test_key_history_identifiers_are_retained_with_a_diagnostic(kind: str) -> None:
    arxiv = "2509.01002"
    value = "10.48550/arxiv.2509.01002" if kind == "doi" else "https://arxiv.org/abs/2509.01002"
    key = "one-" + hash_exact_legacy_identifier(arxiv)
    alias = "old-" + hash_exact_legacy_identifier(value)
    history = (KeyHistory(key, "arxiv", arxiv), KeyHistory(alias, kind, value))
    record = IdentifierRecord("arxiv", {"arxiv": arxiv, kind: value}, key_history=history)
    aggregate = _workspace(record, alias=alias)

    report = normalize_identifier_inventory(
        aggregate.bibliography, aggregate.identifiers, remove_urls=True, remove_arxiv_dois=True
    )

    assert not report.changes.changed
    assert any("key-provenance" in diagnostic for diagnostic in report.diagnostics)
    assert record.identifiers[kind] == value
    assert record.key_history == history
    aggregate.validate()


@pytest.mark.parametrize("kind", ["doi", "url"])
def test_main_identifier_is_retained_without_rekeying(kind: str) -> None:
    value = "10.48550/arxiv.2509.01002" if kind == "doi" else "https://arxiv.org/abs/2509.01002"
    record = IdentifierRecord(kind, {"arxiv": "2509.01002", kind: value})
    aggregate = _workspace(record)

    report = normalize_identifier_inventory(
        aggregate.bibliography, aggregate.identifiers, remove_urls=True, remove_arxiv_dois=True
    )

    assert not report.changes.changed
    assert any("key-provenance" in diagnostic for diagnostic in report.diagnostics)
    assert record.identifiers[kind] == value
    aggregate.validate()


@pytest.mark.parametrize("redundant_primary", [False, True])
def test_cleanup_does_not_orphan_or_promote_distinct_alternates(redundant_primary: bool) -> None:
    derived = "10.48550/arxiv.2509.01002"
    publisher = "10.1000/published"
    primary, alternate = (derived, publisher) if redundant_primary else (publisher, derived)
    record = IdentifierRecord(
        "arxiv", {"arxiv": "2509.01002", "doi": primary}, {"doi": (alternate,)}
    )
    aggregate = _workspace(record)

    report = normalize_identifier_inventory(
        aggregate.bibliography, aggregate.identifiers, remove_urls=True, remove_arxiv_dois=True
    )

    assert record.identifiers["doi"] == primary
    if redundant_primary:
        assert record.identifier_alternates == {"doi": (publisher,)}
        assert not report.changes.changed
        assert any("remaining-alternates" in diagnostic for diagnostic in report.diagnostics)
    else:
        assert record.identifier_alternates == {}
        assert report.changes.changed
    aggregate.validate()

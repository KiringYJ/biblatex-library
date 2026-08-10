"""Contract tests for the read-only legacy workspace audit."""

from pathlib import Path

from .audit import audit_legacy_workspace

FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "legacy-workspace"
EXPECTED_KINDS = frozenset(
    {
        "acmdl_doi",
        "arxiv",
        "doi",
        "hdl",
        "isbn13",
        "jfm",
        "mrnumber",
        "oclc",
        "url",
        "zbl",
        "zbmath",
    }
)


def _fixture_paths() -> tuple[Path, Path, Path]:
    return (
        FIXTURE_ROOT / "library.bib",
        FIXTURE_ROOT / "identifier_collection.json",
        FIXTURE_ROOT / "add_order.json",
    )


def test_audit_reports_matching_keysets_and_physical_order() -> None:
    """Audit reports exact agreement across all three legacy inputs."""
    report = audit_legacy_workspace(*_fixture_paths())

    assert report.keysets_match
    assert report.physical_order_matches


def test_audit_reports_all_eleven_identifier_kinds() -> None:
    """Audit discovers every identifier kind from fixture data."""
    report = audit_legacy_workspace(*_fixture_paths())

    assert report.identifier_kinds == EXPECTED_KINDS


def test_audit_verifies_each_historical_main_identifier_hash() -> None:
    """Audit matches every citekey suffix to its exact legacy main value."""
    report = audit_legacy_workspace(*_fixture_paths())

    assert report.historical_hash_matches == report.identifier_keys


def test_audit_does_not_modify_explicit_input_paths() -> None:
    """Audit leaves the bytes of every explicitly supplied input unchanged."""
    paths = _fixture_paths()
    before = tuple(path.read_bytes() for path in paths)

    audit_legacy_workspace(*paths)

    assert tuple(path.read_bytes() for path in paths) == before


def test_audit_reports_sha256_for_each_input() -> None:
    """Audit records a full SHA-256 digest for each legacy input."""
    report = audit_legacy_workspace(*_fixture_paths())

    assert all(
        len(digest) == 64
        for digest in (
            report.bibliography_sha256,
            report.identifiers_sha256,
            report.add_order_sha256,
        )
    )

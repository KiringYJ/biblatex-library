"""Tests for canonical bibliography validation."""

import hashlib

import bibtexparser
import pytest

from biblio.bibliography import Bibliography, IdentityIndex
from biblio.validate import validate_bibliography


def _bibliography(source: str) -> Bibliography:
    library = bibtexparser.parse_string(source)
    return Bibliography(library.blocks, IdentityIndex(library.entries))


def test_valid_biblatex_record_passes_without_legacy_json() -> None:
    suffix = hashlib.sha256(b"2101.00001").hexdigest()[:8]
    bibliography = _bibliography(
        f"@online{{doe-2020-{suffix},author={{Doe, Jane}},title={{Work}},date={{2020}},"
        "eprint={2101.00001},eprinttype={arxiv},ids={old-key}}"
    )

    result = validate_bibliography(bibliography)

    assert result.valid
    assert result.issues == ()


def test_validation_reports_citekey_and_biblatex_semantic_issues() -> None:
    bibliography = _bibliography(
        "@online{BadKey,author={Doe, Jane},date={2020},eprinttype={arxiv},eprintclass={math.AG}}"
    )

    result = validate_bibliography(bibliography)

    assert not result.valid
    assert any("generated citekey shape" in issue for issue in result.issues)
    assert any("no title-bearing field" in issue for issue in result.issues)
    assert any("without a nonempty eprint" in issue for issue in result.issues)


def test_eprintclass_requires_a_supported_preprint_provider() -> None:
    suffix = hashlib.sha256(b"x").hexdigest()[:8]
    bibliography = _bibliography(
        f"@online{{doe-2020-{suffix},title={{Work}},eprint={{x}},eprintclass={{math.AG}}}}"
    )

    result = validate_bibliography(bibliography)

    assert result.issues == (
        f"entry 'doe-2020-{suffix}' has eprintclass without eprinttype=arxiv or hexagon",
    )


@pytest.mark.parametrize(
    "marker",
    ["eprinttype={hexagon}", "archiveprefix={Hexagon}", "EPRINTTYPE={ HEXAGON }"],
)
def test_hexagon_eprintclass_is_valid_and_preserved(marker: str) -> None:
    suffix = hashlib.sha256(b"2610.00311").hexdigest()[:8]
    bibliography = _bibliography(
        f"@online{{unknown-2026-{suffix},title={{Work}},{marker},"
        "eprint={2610.00311},EPRINTCLASS={math.NT}}"
    )

    result = validate_bibliography(bibliography)

    assert result.valid
    assert not result.issues
    assert next(iter(bibliography)).fields_dict["EPRINTCLASS"].value == "math.NT"


def test_eprintclass_still_rejects_an_unknown_provider() -> None:
    bibliography = _bibliography(
        "@online{unknown-2026-00000000,title={Work},eprinttype={HAL},"
        "eprint={2610.00311},eprintclass={math.NT}}"
    )
    result = validate_bibliography(bibliography)
    assert not result.valid
    assert any(
        "eprintclass without eprinttype=arxiv or hexagon" in issue for issue in result.issues
    )


def test_hexagon_class_alias_conflicts_are_invalid() -> None:
    bibliography = _bibliography(
        "@online{unknown-2026-fffec23f,title={Work},eprinttype={hexagon},"
        "eprint={2610.00311},primaryclass={math.NT},eprintclass={math.AG}}"
    )
    result = validate_bibliography(bibliography)
    assert not result.valid
    assert any("conflicting Hexagon class aliases" in issue for issue in result.issues)


def test_bibliography_validation_leaves_exact_hash_proof_to_workspace_json() -> None:
    bibliography = _bibliography(
        "@book{doe-2020-deadbeef,author={Doe, Jane},title={Work},date={2020}}"
    )

    result = validate_bibliography(bibliography)

    assert result.valid

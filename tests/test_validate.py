"""Tests for canonical bibliography validation."""

import hashlib

import bibtexparser

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


def test_eprintclass_requires_arxiv_semantics() -> None:
    suffix = hashlib.sha256(b"x").hexdigest()[:8]
    bibliography = _bibliography(
        f"@online{{doe-2020-{suffix},title={{Work}},eprint={{x}},eprintclass={{math.AG}}}}"
    )

    result = validate_bibliography(bibliography)

    assert result.issues == (f"entry 'doe-2020-{suffix}' has eprintclass without eprinttype=arxiv",)


def test_bibliography_validation_leaves_exact_hash_proof_to_workspace_json() -> None:
    bibliography = _bibliography(
        "@book{doe-2020-deadbeef,author={Doe, Jane},title={Work},date={2020}}"
    )

    result = validate_bibliography(bibliography)

    assert result.valid

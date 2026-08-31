"""Integration tests for coordinated workspace application services."""

import ast
import hashlib
import os
from dataclasses import replace
from pathlib import Path

import bibtexparser
import pytest

from biblio import commands
from biblio.add_entries import prepare_entries, prepare_staged_sources, select_main_identifier
from biblio.identifier_collection import (
    IdentifierRecord,
    identifiers_from_entry,
    parse_add_order,
    parse_identifier_collection,
    serialize_add_order,
    serialize_identifier_collection,
)
from biblio.normalize.pipeline import NORMALIZATION_ACTIONS
from biblio.results import CommitOutcome
from biblio.storage import (
    BibliographyCodec,
    WorkspacePaths,
    WorkspaceRecoveryResult,
    read_workspace_snapshot,
)


def _workspace(tmp_path: Path, source: str = "") -> WorkspacePaths:
    bibliography = tmp_path / "library.bib"
    identifiers = tmp_path / "identifier_collection.json"
    add_order = tmp_path / "add_order.json"
    bibliography.write_text(source, encoding="utf-8")
    parsed = BibliographyCodec.parse_bytes(bibliography.read_bytes())
    records: dict[str, IdentifierRecord] = {}
    order: list[str] = []
    for entry in parsed:
        inventory = identifiers_from_entry(entry)
        main, _value = select_main_identifier(inventory)
        records[entry.key] = IdentifierRecord(main, inventory)
        order.append(entry.key)
    identifiers.write_bytes(serialize_identifier_collection(records))
    add_order.write_bytes(serialize_add_order(order))
    return WorkspacePaths(bibliography, identifiers, add_order)


def _key(stem: str, identifier: str) -> str:
    return f"{stem}-{hashlib.sha256(identifier.encode()).hexdigest()[:8]}"


def _staged(path: Path, *, doi: str = "10.1000/work", extra: str = "") -> None:
    path.write_text(
        f"@article{{x,author={{Doe, Jane}},date={{2024}},title={{Work}},doi={{{doi}}}{extra}}}\n",
        encoding="utf-8",
    )


def _pending_receipt(
    paths: WorkspacePaths,
    staged: Path,
    *,
    original: commands.WorkspaceDigestVector | None = None,
    candidate: commands.WorkspaceDigestVector | None = None,
) -> commands._CleanupReceipt:
    current = commands._snapshot_vector(read_workspace_snapshot(paths))
    prepared = prepare_staged_sources(((staged, staged.read_bytes()),))
    entries = tuple(commands._added_entry_manifest(entry) for entry in prepared.entries)
    added_keys = prepared.files[0].keys
    return commands._CleanupReceipt(
        "0" * 32,
        added_keys,
        original or current,
        candidate or commands.WorkspaceDigestVector("f" * 64, "f" * 64, "f" * 64),
        (
            commands._ReceiptItem(
                staged.name,
                hashlib.sha256(staged.read_bytes()).hexdigest(),
                added_keys,
                entries,
            ),
        ),
        (staged.name,),
    )


def _workspace_bytes(paths: WorkspacePaths) -> tuple[bytes, bytes, bytes]:
    return (
        paths.bibliography.read_bytes(),
        paths.identifiers.read_bytes(),
        paths.add_order.read_bytes(),
    )


def _idle_transaction_id(paths: WorkspacePaths) -> str:
    status = commands.inspect_workspace_recovery(paths)
    assert status.coordinator is not None
    transaction_id = status.coordinator.get("txid")
    assert isinstance(transaction_id, str)
    return transaction_id


def test_validate_reads_all_three_without_creating_sidecars(tmp_path: Path) -> None:
    paths = _workspace(tmp_path)
    before = set(tmp_path.iterdir())

    result = commands.validate(paths)

    assert result.valid
    assert set(tmp_path.iterdir()) == before


def test_validate_reports_cross_artifact_mismatch(tmp_path: Path) -> None:
    paths = _workspace(tmp_path)
    paths.add_order.write_text('["missing"]\n', encoding="utf-8")

    result = commands.validate(paths)

    assert not result.valid
    assert any("canonical keysets differ" in issue for issue in result.issues)


def test_audit_is_read_only_and_reports_bibliography_compliance(tmp_path: Path) -> None:
    doi = "10.1000/audit"
    key = _key("doe-2024", doi)
    paths = _workspace(
        tmp_path,
        f"@article{{{key},author={{Doe, Jane}},date={{2024}},title={{Work}},"
        f"journal={{J. Test}},fjournal={{Journal of Tests}},doi={{{doi}}}}}\n",
    )
    before = _workspace_bytes(paths)

    result = commands.audit(paths)

    assert not result.clean
    assert [finding.code for finding in result.findings] == [
        "legacy-journal-field",
        "legacy-journal-field",
    ]
    assert _workspace_bytes(paths) == before


def test_add_directory_orders_weird_names_and_consumes_only_bib_files(tmp_path: Path) -> None:
    paths = _workspace(tmp_path)
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "nested").mkdir()
    _staged(staging / "z strange [2].bib", doi="10.1000/z")
    _staged(staging / "! first.BIB", doi="10.1000/a")
    (staging / "ignore.txt").write_text("no", encoding="utf-8")
    _staged(staging / "nested" / "ignored.bib", doi="10.1000/nested")

    result = commands.add(paths, staging)

    expected = prepare_entries(
        (
            bibtexparser.parse_string(
                "@article{a,author={Doe, Jane},date={2024},title={Work},doi={10.1000/a}}"
            ).entries[0],
            bibtexparser.parse_string(
                "@article{z,author={Doe, Jane},date={2024},title={Work},doi={10.1000/z}}"
            ).entries[0],
        )
    )
    assert result.added_keys == tuple(entry.key for entry in expected)
    assert result.commit is not None
    assert result.commit.outcome is CommitOutcome.COMMITTED_VERIFIED
    assert not (staging / "! first.BIB").exists()
    assert not (staging / "z strange [2].bib").exists()
    assert (staging / "ignore.txt").exists()
    assert (staging / "nested" / "ignored.bib").exists()
    assert parse_add_order(paths.add_order.read_bytes()) == result.added_keys


def test_add_keeps_nonredundant_inventory_and_uses_arxiv_for_derived_doi(tmp_path: Path) -> None:
    paths = _workspace(tmp_path)
    staged = tmp_path / "opaque.bib"
    staged.write_text(
        "@online{x,author={Doe, Jane},date={2020},title={X},"
        "doi={https://doi.org/10.48550/arXiv.2101.00001},"
        "eprint={2101.00001},eprinttype={arxiv},isbn={978-1-4028-9462-6},"
        "url={https://example.test},mrnumber={MR1},zbl={Z},zbmath={B},jfm={J},"
        "oclc={O},hdl={H},acmdl_doi={10.1145/A}}",
        encoding="utf-8",
    )

    result = commands.add(paths, staged, dry_run=True)

    expected_suffix = hashlib.sha256(b"2101.00001").hexdigest()[:8]
    assert result.added_keys == (f"doe-2020-{expected_suffix}",)
    assert staged.exists()

    committed = commands.add(paths, staged)
    record = parse_identifier_collection(paths.identifiers.read_bytes())[committed.added_keys[0]]
    assert record.main_identifier == "arxiv"
    assert set(record.identifiers) == {
        "isbn13",
        "arxiv",
        "url",
        "mrnumber",
        "zbl",
        "zbmath",
        "jfm",
        "oclc",
        "hdl",
        "acmdl_doi",
    }
    assert "doi" not in record.identifiers
    entry = BibliographyCodec.parse_bytes(paths.bibliography.read_bytes()).resolve(
        committed.added_keys[0]
    )
    assert "doi" not in entry.fields_dict
    assert entry.fields_dict["eprint"].value == "2101.00001"
    assert commands.validate(paths).valid


@pytest.mark.parametrize("use_template", [False, True])
def test_add_removes_redundant_arxiv_doi_and_url_from_bibliography_and_json(
    tmp_path: Path, use_template: bool
) -> None:
    paths = _workspace(tmp_path)
    staged = tmp_path / "collins.bib"
    arxiv = "2509.01002"
    doi = "10.48550/arxiv.2509.01002"
    source = (
        "@online{temporary,title={An Introduction to Conifold Transitions},"
        "author={Collins, Tristan C.},date={2025},eprintclass={math.DG},"
        f"eprint={{{arxiv}}},eprinttype={{arxiv}},doi={{{doi}}},"
        f"url={{https://doi.org/{doi}}}}}\n"
    )
    staged.write_text(source, encoding="utf-8")
    companion = staged.with_suffix(".json")
    if use_template:
        commands.template(staged)
        template = parse_identifier_collection(companion.read_bytes())["temporary"]
        assert template.main_identifier == "arxiv"
        assert template.identifiers == {"arxiv": arxiv}
    before = _workspace_bytes(paths)

    preview = commands.add(paths, staged, dry_run=True)

    key = _key("collins-2025", arxiv)
    assert preview.added_keys == (key,)
    assert [(delta.field, delta.before, delta.after) for delta in preview.changes.field_deltas] == [
        ("url", f"https://doi.org/{doi}", None),
        ("doi", doi, None),
    ]
    assert _workspace_bytes(paths) == before
    assert staged.read_text(encoding="utf-8") == source
    assert companion.exists() is use_template

    committed = commands.add(paths, staged)

    assert committed.added_keys == (key,)
    entry = BibliographyCodec.parse_bytes(paths.bibliography.read_bytes()).resolve(key)
    assert "doi" not in entry.fields_dict
    assert "url" not in entry.fields_dict
    assert entry.fields_dict["eprint"].value == arxiv
    record = parse_identifier_collection(paths.identifiers.read_bytes())[key]
    assert record.main_identifier == "arxiv"
    assert record.identifiers == {"arxiv": arxiv}
    assert commands.validate(paths).valid
    assert not commands.normalize(paths, "all").changes.changed
    assert not staged.exists()
    assert not companion.exists()


def test_reviewed_doi_selection_survives_arxiv_doi_cleanup(tmp_path: Path) -> None:
    paths = _workspace(tmp_path)
    staged = tmp_path / "reviewed.bib"
    doi = "10.48550/arxiv.2509.01002"
    _staged(staged, doi=doi, extra=",eprint={2509.01002},eprinttype={arxiv}")
    commands.template(staged)
    companion = staged.with_suffix(".json")
    records = parse_identifier_collection(companion.read_bytes())
    records["x"].identifiers["doi"] = doi
    records["x"].main_identifier = "doi"
    companion.write_bytes(serialize_identifier_collection(records))

    result = commands.add(paths, staged)

    key = _key("doe-2024", doi)
    assert result.added_keys == (key,)
    entry = BibliographyCodec.parse_bytes(paths.bibliography.read_bytes()).resolve(key)
    assert "doi" not in entry.fields_dict
    record = parse_identifier_collection(paths.identifiers.read_bytes())[key]
    assert record == records["x"]
    assert commands.validate(paths).valid


def test_add_prunes_redundant_identifiers_from_an_existing_reviewed_template(
    tmp_path: Path,
) -> None:
    paths = _workspace(tmp_path)
    staged = tmp_path / "incomplete.bib"
    _staged(
        staged,
        doi="10.48550/arxiv.2509.01002",
        extra=",eprint={2509.01002},eprinttype={arxiv}",
    )
    commands.template(staged)
    companion = staged.with_suffix(".json")
    records = parse_identifier_collection(companion.read_bytes())
    records["x"].identifiers["doi"] = "10.48550/arxiv.2509.01002"
    records["x"].identifiers["url"] = "https://arxiv.org/abs/2509.01002"
    companion.write_bytes(serialize_identifier_collection(records))
    before = _workspace_bytes(paths)

    preview = commands.add(paths, staged, dry_run=True)

    assert preview.added_keys == (_key("doe-2024", "2509.01002"),)
    assert _workspace_bytes(paths) == before
    assert staged.exists()
    assert companion.exists()
    assert parse_identifier_collection(companion.read_bytes()) == records

    result = commands.add(paths, staged)

    record = parse_identifier_collection(paths.identifiers.read_bytes())[result.added_keys[0]]
    assert record.identifiers == {"arxiv": "2509.01002"}
    assert record.main_identifier == "arxiv"
    assert commands.validate(paths).valid


def test_add_spaced_arxiv_marker_uses_eprint_and_validate_rejects_wrong_json_main(
    tmp_path: Path,
) -> None:
    paths = _workspace(tmp_path)
    staged = tmp_path / "opaque.bib"
    staged.write_text(
        "@online{x,author={Doe, Jane},date={2020},title={X},"
        "doi={10.48550/arXiv.2101.00001},eprint={2101.00001},"
        "eprinttype={ arXiv }}",
        encoding="utf-8",
    )

    added = commands.add(paths, staged, dry_run=True)

    arxiv_key = _key("doe-2020", "2101.00001")
    assert added.added_keys == (arxiv_key,)

    committed = commands.add(paths, staged)
    records = parse_identifier_collection(paths.identifiers.read_bytes())
    record = records[committed.added_keys[0]]
    assert "doi" not in record.identifiers
    record.identifiers["doi"] = "10.48550/arxiv.2101.00001"
    record.main_identifier = "doi"
    paths.identifiers.write_bytes(serialize_identifier_collection(records))

    validation = commands.validate(paths)
    assert not validation.valid
    assert any("does not match exact identifier hash" in issue for issue in validation.issues)


def test_add_normalizes_incoming_entries_before_key_derivation_and_validates_candidate(
    tmp_path: Path,
) -> None:
    paths = _workspace(tmp_path)
    staged = tmp_path / "book.bib"
    staged.write_text(
        r"@book{temporary,author={Doe , Jane},year={2020},title={\LaTeX Book},"
        "isbn={0-387-97926-3},pages={100},publisher={Springer, Cham}}\n",
        encoding="utf-8",
    )

    preview = commands.add(paths, staged, dry_run=True)

    normalized_isbn = "9780387979267"
    expected_key = _key("doe-2020", normalized_isbn)
    assert preview.added_keys == (expected_key,)
    assert preview.normalization_actions == NORMALIZATION_ACTIONS
    assert {delta.field for delta in preview.changes.field_deltas} == {
        "author",
        "date",
        "isbn",
        "year",
    }
    assert all(delta.canonical_key == expected_key for delta in preview.changes.field_deltas)
    assert _workspace_bytes(paths) == (b"", b"{}\n", b"[]\n")
    assert staged.exists()

    committed = commands.add(paths, staged)

    assert committed.added_keys == (expected_key,)
    entry = BibliographyCodec.parse_bytes(paths.bibliography.read_bytes()).resolve(expected_key)
    assert str(entry.fields_dict["author"].value) == "Doe, Jane"
    assert str(entry.fields_dict["title"].value) == r"\LaTeX Book"
    assert str(entry.fields_dict["publisher"].value) == "Springer, Cham"
    assert str(entry.fields_dict["date"].value) == "2020"
    assert str(entry.fields_dict["isbn"].value) == normalized_isbn
    assert str(entry.fields_dict["pages"].value) == "100"
    assert "year" not in entry.fields_dict
    assert "pagetotal" not in entry.fields_dict
    assert "location" not in entry.fields_dict
    record = parse_identifier_collection(paths.identifiers.read_bytes())[expected_key]
    assert record.main_identifier == "isbn13"
    assert record.identifiers == {"isbn13": normalized_isbn}
    assert commands.validate(paths).valid


def test_arxiv_misc_template_add_restores_online_without_rewriting_staging(tmp_path: Path) -> None:
    paths = _workspace(tmp_path)
    staged = tmp_path / "arxiv.bib"
    arxiv = "2602.21791v2"
    source = (
        "@misc{temporary,author={Doe, Jane},year={2026},title={Preprint},"
        f"archiveprefix={{arXiv}},primaryclass={{math.AG}},eprint={{{arxiv}}}}}\n"
    )
    staged.write_text(source, encoding="utf-8")

    commands.template(staged)
    companion = staged.with_suffix(".json")
    template_bytes = companion.read_bytes()
    preview = commands.add(paths, staged, dry_run=True)

    key = _key("doe-2026", arxiv)
    assert preview.added_keys == (key,)
    assert staged.read_text(encoding="utf-8") == source
    assert companion.read_bytes() == template_bytes
    assert _workspace_bytes(paths) == (b"", b"{}\n", b"[]\n")
    type_changes = [delta for delta in preview.changes.field_deltas if delta.field == "entry_type"]
    assert [(delta.canonical_key, delta.before, delta.after) for delta in type_changes] == [
        (key, "misc", "online")
    ]

    result = commands.add(paths, staged)

    assert result.added_keys == (key,)
    entry = BibliographyCodec.parse_bytes(paths.bibliography.read_bytes()).resolve(key)
    assert entry.entry_type == "online"
    assert entry.fields_dict["eprint"].value == arxiv
    assert entry.fields_dict["eprinttype"].value == "arxiv"
    record = parse_identifier_collection(paths.identifiers.read_bytes())[key]
    assert record.main_identifier == "arxiv"
    assert record.identifiers == {"arxiv": arxiv}
    assert commands.validate(paths).valid
    assert not commands.normalize(paths, "all").changes.changed


def test_arxiv_type_normalization_preserves_existing_identifier_provenance(tmp_path: Path) -> None:
    arxiv = "2602.21791v2"
    key = _key("doe-2026", arxiv)
    paths = _workspace(
        tmp_path,
        f"@misc{{{key},author={{Doe, Jane}},title={{Preprint}},date={{2026}},"
        f"eprinttype={{arxiv}},eprint={{{arxiv}}}}}\n",
    )
    before = _workspace_bytes(paths)

    preview = commands.normalize(paths, "eprint-fields", dry_run=True)

    assert preview.changes.changed_keys == (key,)
    assert _workspace_bytes(paths) == before

    result = commands.normalize(paths, "eprint-fields")

    assert result.commit is not None
    assert BibliographyCodec.parse_bytes(paths.bibliography.read_bytes()).resolve(
        key
    ).entry_type == ("online")
    assert paths.identifiers.read_bytes() == before[1]
    assert paths.add_order.read_bytes() == before[2]
    assert commands.validate(paths).valid


def test_template_add_completes_doi_url_and_reviewer_cleanup(tmp_path: Path) -> None:
    paths = _workspace(tmp_path)
    staged = tmp_path / "mixed-cleanup.bib"
    dois = ["10.1007/BF01458074", "10.1000/MIXEDCASE"] + [
        f"10.1000/cleanup-{index}" for index in range(2, 8)
    ]
    reviewers = [r"Victor\ Mikhailovich\ Adukov"] + [
        rf"Reviewer{index}\ Family{index}" for index in range(1, 8)
    ]
    sources: list[str] = []
    for index, (doi, reviewer) in enumerate(zip(dois, reviewers, strict=True)):
        url = f",url={{https://doi.org/{doi}}}" if index < 2 else ""
        sources.append(
            f"@article{{item{index},author={{Doe, Jane}},date={{2020}},"
            r"title={Keep $x\ y$},"
            f"doi={{{doi}}},mrreviewer={{{reviewer}}}{url}}}"
        )
    source = "\n".join(sources) + "\n"
    staged.write_text(source, encoding="utf-8")
    assert sum(value.count("\\ ") for value in reviewers) == 9

    commands.template(staged)
    companion = staged.with_suffix(".json")
    template_bytes = companion.read_bytes()
    preview = commands.add(paths, staged, dry_run=True)

    assert staged.read_text(encoding="utf-8") == source
    assert companion.read_bytes() == template_bytes
    assert _workspace_bytes(paths) == (b"", b"{}\n", b"[]\n")
    removed_urls = [
        delta
        for delta in preview.changes.field_deltas
        if delta.field == "url" and delta.after is None
    ]
    reviewer_changes = [
        delta for delta in preview.changes.field_deltas if delta.field == "mrreviewer"
    ]
    assert len(reviewer_changes) == 8
    assert sum((delta.before or "").count("\\ ") for delta in reviewer_changes) == 9
    assert all(delta.after is not None and "\\ " not in delta.after for delta in reviewer_changes)

    result = commands.add(paths, staged)

    assert result.added_keys == preview.added_keys
    assert len(removed_urls) == 2
    bibliography = BibliographyCodec.parse_bytes(paths.bibliography.read_bytes())
    entries = tuple(bibliography)
    assert len(entries) == 8
    assert all("url" not in entry.fields_dict for entry in entries)
    assert sum(str(entry.fields_dict["mrreviewer"].value).count("\\ ") for entry in entries) == 0
    for entry, original_doi, original_reviewer in zip(entries, dois, reviewers, strict=True):
        assert entry.fields_dict["doi"].value == original_doi.lower()
        assert entry.fields_dict["mrreviewer"].value == original_reviewer.replace("\\ ", " ")
        assert entry.fields_dict["title"].value == r"Keep $x\ y$"
    assert commands.validate(paths).valid
    assert not commands.normalize(paths, "all").changes.changed


def test_existing_doi_cleanup_preserves_exact_legacy_doi_and_prunes_json_url(
    tmp_path: Path,
) -> None:
    doi = "10.1007/BF01458074"
    key = _key("doe-2020", doi)
    paths = _workspace(
        tmp_path,
        f"@article{{{key},author={{Doe, Jane}},date={{2020}},title={{Work}},"
        f"doi={{{doi}}},url={{https://doi.org/{doi.lower()}}},"
        r"mrreviewer={Victor\ Mikhailovich\ Adukov}}" + "\n",
    )
    before = _workspace_bytes(paths)

    preview = commands.normalize(paths, "all", dry_run=True)

    assert preview.changes.changed_keys == (key,)
    assert _workspace_bytes(paths) == before

    result = commands.normalize(paths, "all")

    assert result.commit is not None
    entry = BibliographyCodec.parse_bytes(paths.bibliography.read_bytes()).resolve(key)
    assert entry.fields_dict["doi"].value == doi
    assert "url" not in entry.fields_dict
    assert entry.fields_dict["mrreviewer"].value == "Victor Mikhailovich Adukov"
    record = parse_identifier_collection(paths.identifiers.read_bytes())[key]
    assert record.identifiers == {"doi": doi}
    assert record.main_identifier == "doi"
    assert paths.add_order.read_bytes() == before[2]
    assert commands.validate(paths).valid


def test_add_consumes_accent_arguments_without_removing_formatting_groups(tmp_path: Path) -> None:
    paths = _workspace(tmp_path)
    staged = tmp_path / "accent-arguments.bib"
    source = (
        r"@article{temporary,author={Z\'{u}\~{n}iga, Elena},date={2020},"
        r"title={\textbf{Z\'{u}\~{n}iga}},mrreviewer={Z\'{u}\~{n}iga\ Reviewer},"
        "doi={10.1007/BF01458074},url={https://doi.org/10.1007/BF01458074}}\n"
    )
    staged.write_text(source, encoding="utf-8")

    preview = commands.add(paths, staged, dry_run=True)

    key = _key("zuniga-2020", "10.1007/bf01458074")
    assert preview.added_keys == (key,)
    assert staged.read_text(encoding="utf-8") == source
    assert _workspace_bytes(paths) == (b"", b"{}\n", b"[]\n")

    added = commands.add(paths, staged)

    assert added.added_keys == (key,)
    entry = BibliographyCodec.parse_bytes(paths.bibliography.read_bytes()).resolve(key)
    assert entry.fields_dict["author"].value == "Zúñiga, Elena"
    assert entry.fields_dict["title"].value == r"\textbf{Zúñiga}"
    assert entry.fields_dict["mrreviewer"].value == "Zúñiga Reviewer"
    assert entry.fields_dict["doi"].value == "10.1007/bf01458074"
    assert "url" not in entry.fields_dict
    assert commands.validate(paths).valid
    assert not commands.normalize(paths, "all").changes.changed


def test_template_and_add_preserve_reviewed_isbn_provenance(tmp_path: Path) -> None:
    paths = _workspace(tmp_path)
    staged = tmp_path / "book.bib"
    source = (
        r"@book{temporary,author={Doe , Jane},year={2020},title={\LaTeX Book},"
        "isbn={0-387-97926-3},pages={100},publisher={Springer, Cham}}\n"
    )
    staged.write_text(source, encoding="utf-8")

    generated = commands.template(staged)

    companion = staged.with_suffix(".json")
    assert generated.created_paths == (companion,)
    assert staged.read_text(encoding="utf-8") == source
    records = parse_identifier_collection(companion.read_bytes())
    assert records["temporary"].identifiers["isbn13"] == "9780387979267"
    reviewed_isbn = "978-0-387-97926-7"
    records["temporary"].identifiers["isbn13"] = reviewed_isbn
    reviewed_bytes = serialize_identifier_collection(records)
    companion.write_bytes(reviewed_bytes)

    preview = commands.add(paths, staged, dry_run=True)

    expected_key = _key("doe-2020", reviewed_isbn)
    assert preview.added_keys == (expected_key,)
    assert companion.read_bytes() == reviewed_bytes
    assert staged.read_text(encoding="utf-8") == source

    committed = commands.add(paths, staged)

    assert committed.added_keys == preview.added_keys
    entry = BibliographyCodec.parse_bytes(paths.bibliography.read_bytes()).resolve(expected_key)
    assert entry.fields_dict["isbn"].value == "9780387979267"
    assert entry.fields_dict["author"].value == "Doe, Jane"
    assert entry.fields_dict["title"].value == r"\LaTeX Book"
    assert entry.fields_dict["publisher"].value == "Springer, Cham"
    assert entry.fields_dict["pages"].value == "100"
    stored_record = parse_identifier_collection(paths.identifiers.read_bytes())[expected_key]
    assert stored_record.identifiers["isbn13"] == reviewed_isbn
    assert commands.validate(paths).valid


def test_add_normalizes_mr_pair_and_text_without_touching_identifiers(tmp_path: Path) -> None:
    paths = _workspace(tmp_path)
    staged = tmp_path / "mr.bib"
    source = (
        r"""@article{temporary,
  author = {Macr\`\i , Emanuele},
  year = {2020},
  title = {On \textbf{\"O} and \LaTeX},
  journal = {J. Tests},
  fjournal = {Journal of Tests},
  mrclass = {53C},
  doi = {10.1000/mr-example}
}"""
        "\n"
    )
    staged.write_text(source, encoding="utf-8")
    commands.template(staged)
    companion = staged.with_suffix(".json")
    reviewed_bytes = companion.read_bytes()

    preview = commands.add(paths, staged, dry_run=True)

    expected_key = _key("macri-2020", "10.1000/mr-example")
    assert preview.added_keys == (expected_key,)
    assert staged.read_text(encoding="utf-8") == source
    assert companion.read_bytes() == reviewed_bytes
    assert _workspace_bytes(paths) == (b"", b"{}\n", b"[]\n")

    result = commands.add(paths, staged)

    assert result.added_keys == (expected_key,)
    entry = BibliographyCodec.parse_bytes(paths.bibliography.read_bytes()).resolve(expected_key)
    assert entry.fields_dict["author"].value == "Macrì, Emanuele"
    assert entry.fields_dict["title"].value == r"On \textbf{Ö} and \LaTeX"
    assert entry.fields_dict["shortjournal"].value == "J. Tests"
    assert entry.fields_dict["journaltitle"].value == "Journal of Tests"
    assert entry.fields_dict["doi"].value == "10.1000/mr-example"
    assert "journal" not in entry.fields_dict and "fjournal" not in entry.fields_dict
    assert commands.validate(paths).valid
    assert not commands.normalize(paths, "all").changes.changed


def test_add_mr_gates_use_bib_fields_not_json_only_identifiers(tmp_path: Path) -> None:
    paths = _workspace(tmp_path)
    staged = tmp_path / "mixed.bib"
    sources = (
        ("markedbook", "book", "pages={xiv+123},mrclass={53C}"),
        ("plainbook", "book", "pages={xiv+123}"),
        ("markedjournal", "article", "journal={Short},fjournal={Full},mrreviewer={Reviewer}"),
        ("plainjournal", "article", "journal={Short},fjournal={Full}"),
    )
    source = (
        "\n".join(
            f"@{kind}{{{key},author={{Doe, Jane}},title={{Work}},date={{2020}},"
            f"doi={{10.1000/{key}}},{fields}}}"
            for key, kind, fields in sources
        )
        + "\n"
    )
    staged.write_text(source, encoding="utf-8")
    commands.template(staged)
    companion = staged.with_suffix(".json")
    records = parse_identifier_collection(companion.read_bytes())
    for key in ("plainbook", "plainjournal"):
        records[key].identifiers["mrnumber"] = "MR" + key
    reviewed_bytes = serialize_identifier_collection(records)
    companion.write_bytes(reviewed_bytes)

    preview = commands.add(paths, staged, dry_run=True)

    keys = {key: _key("doe-2020", f"10.1000/{key}") for key, _kind, _fields in sources}
    assert preview.added_keys == tuple(keys.values())
    assert staged.read_text(encoding="utf-8") == source
    assert companion.read_bytes() == reviewed_bytes
    assert _workspace_bytes(paths) == (b"", b"{}\n", b"[]\n")

    result = commands.add(paths, staged)

    assert result.added_keys == preview.added_keys
    bibliography = BibliographyCodec.parse_bytes(paths.bibliography.read_bytes())
    assert bibliography.resolve(keys["markedbook"]).fields_dict["pagetotal"].value == "xiv+123"
    assert "pages" not in bibliography.resolve(keys["markedbook"]).fields_dict
    assert bibliography.resolve(keys["plainbook"]).fields_dict["pages"].value == "xiv+123"
    assert "pagetotal" not in bibliography.resolve(keys["plainbook"]).fields_dict
    assert bibliography.resolve(keys["markedjournal"]).fields_dict["shortjournal"].value == "Short"
    assert bibliography.resolve(keys["markedjournal"]).fields_dict["journaltitle"].value == "Full"
    assert bibliography.resolve(keys["plainjournal"]).fields_dict["journal"].value == "Short"
    assert bibliography.resolve(keys["plainjournal"]).fields_dict["fjournal"].value == "Full"
    stored = parse_identifier_collection(paths.identifiers.read_bytes())
    for key in ("plainbook", "plainjournal"):
        assert stored[keys[key]].identifiers["mrnumber"] == "MR" + key
        assert "mrnumber" not in bibliography.resolve(keys[key]).fields_dict
    assert commands.validate(paths).valid
    assert not commands.normalize(paths, "all").changes.changed


def test_template_reviews_each_entry_and_add_honors_selected_main_identifiers(
    tmp_path: Path,
) -> None:
    paths = _workspace(tmp_path)
    staged = tmp_path / "batch.bib"
    staged.write_text(
        "@article{first,author={Doe, Jane},year={2020},title={First},"
        "doi={10.1000/first},eprint={2001.00001},eprinttype={arxiv}}\n"
        "@online{second,author={Roe, Richard},year={2021},title={Second},"
        "url={https://example.test/second}}\n",
        encoding="utf-8",
    )

    generated = commands.template(staged)

    template_path = staged.with_suffix(".json")
    assert generated.created_paths == (template_path,)
    records = parse_identifier_collection(template_path.read_bytes())
    assert tuple(records) == ("first", "second")
    assert records["first"].main_identifier == "doi"
    assert records["second"].main_identifier == "url"

    records["first"].main_identifier = "arxiv"
    records["second"].identifiers["hdl"] = "20.5000/second"
    records["second"].main_identifier = "hdl"
    template_path.write_bytes(serialize_identifier_collection(records))

    preview = commands.add(paths, staged, dry_run=True)

    first_key = _key("doe-2020", "2001.00001")
    second_key = _key("roe-2021", "20.5000/second")
    assert preview.added_keys == (first_key, second_key)
    assert preview.input_paths == (staged.resolve(), template_path.resolve())
    assert staged.exists()
    assert template_path.exists()

    committed = commands.add(paths, staged)

    assert committed.added_keys == (first_key, second_key)
    committed_records = parse_identifier_collection(paths.identifiers.read_bytes())
    assert committed_records[first_key].main_identifier == "arxiv"
    assert committed_records[first_key].identifiers == {
        "doi": "10.1000/first",
        "arxiv": "2001.00001",
    }
    assert committed_records[second_key].main_identifier == "hdl"
    assert committed_records[second_key].identifiers == {
        "url": "https://example.test/second",
        "hdl": "20.5000/second",
    }
    assert commands.validate(paths).valid
    assert not staged.exists()
    assert not template_path.exists()


def test_add_rejects_an_incomplete_multi_entry_template_without_mutation(
    tmp_path: Path,
) -> None:
    paths = _workspace(tmp_path)
    staged = tmp_path / "batch.bib"
    staged.write_text(
        "@article{first,author={Doe, Jane},date={2020},title={First},doi={10.1000/first}}\n"
        "@article{second,author={Roe, Richard},date={2021},title={Second},"
        "doi={10.1000/second}}\n",
        encoding="utf-8",
    )
    commands.template(staged)
    template_path = staged.with_suffix(".json")
    records = parse_identifier_collection(template_path.read_bytes())
    del records["second"]
    template_path.write_bytes(serialize_identifier_collection(records))
    before = _workspace_bytes(paths)

    with pytest.raises(ValueError, match="keys must exactly match"):
        commands.add(paths, staged)

    assert _workspace_bytes(paths) == before
    assert staged.exists()
    assert template_path.exists()


def test_add_validation_failure_preserves_workspace_and_staging(tmp_path: Path) -> None:
    paths = _workspace(tmp_path)
    staged = tmp_path / "missing-title.bib"
    staged.write_text(
        "@article{temporary,author={Doe, Jane},year={2020},doi={10.1000/work}}\n",
        encoding="utf-8",
    )
    before = _workspace_bytes(paths)

    with pytest.raises(ValueError, match="has no title-bearing field"):
        commands.add(paths, staged)

    assert _workspace_bytes(paths) == before
    assert staged.exists()


def test_add_rejects_explicit_non_bib_and_preserves_dry_run(tmp_path: Path) -> None:
    paths = _workspace(tmp_path)
    wrong = tmp_path / "input.txt"
    wrong.write_text("x", encoding="utf-8")
    staged = tmp_path / "opaque.bib"
    _staged(staged)

    with pytest.raises(ValueError, match="must have a .bib suffix"):
        commands.add(paths, wrong)
    result = commands.add(paths, staged, dry_run=True)

    assert result.commit is None
    assert result.retained_paths == (staged.resolve(),)
    assert staged.exists()


def test_add_changed_file_after_commit_is_retained_as_conflict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _workspace(tmp_path)
    staged = tmp_path / "opaque.bib"
    _staged(staged)
    original_write = commands._write_receipt

    def write_then_change(directory: Path, receipt: commands._CleanupReceipt) -> None:
        original_write(directory, receipt)
        staged.write_text("changed", encoding="utf-8")

    monkeypatch.setattr(commands, "_write_receipt", write_then_change)

    result = commands.add(paths, staged)

    assert result.commit is not None
    assert result.commit.outcome is CommitOutcome.COMMITTED_VERIFIED
    assert result.conflicted_paths == (staged.resolve(),)
    assert staged.exists()
    assert (tmp_path / commands._RECEIPT_NAME).exists()


def test_add_changed_template_after_commit_retains_the_staging_pair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _workspace(tmp_path)
    staged = tmp_path / "opaque.bib"
    _staged(staged)
    commands.template(staged)
    template_path = staged.with_suffix(".json")
    original_write = commands._write_receipt
    mutated = False

    def write_then_change(directory: Path, receipt: commands._CleanupReceipt) -> None:
        nonlocal mutated
        original_write(directory, receipt)
        if not mutated:
            mutated = True
            template_path.write_text("{}\n", encoding="utf-8")

    monkeypatch.setattr(commands, "_write_receipt", write_then_change)

    result = commands.add(paths, staged)

    assert result.commit is not None
    assert result.commit.outcome is CommitOutcome.COMMITTED_VERIFIED
    assert result.conflicted_paths == (staged.resolve(), template_path.resolve())
    assert staged.exists()
    assert template_path.exists()
    assert (tmp_path / commands._RECEIPT_NAME).exists()


def test_add_cleanup_treats_crlf_and_lf_inside_fields_as_equivalent(tmp_path: Path) -> None:
    paths = _workspace(tmp_path)
    staged = tmp_path / "multiline-names.bib"
    staged.write_bytes(
        b"@article{x,\r\n"
        b"  author={Doe, Jane and\r\n    Roe, Richard},\r\n"
        b"  editor={Smith, Alex and\r\n    Jones, Taylor},\r\n"
        b"  date={2024},\r\n"
        b"  title={Work},\r\n"
        b"  doi={10.1000/work}\r\n"
        b"}\r\n"
    )
    commands.template(staged)
    template_path = staged.with_suffix(".json")

    result = commands.add(paths, staged)

    assert result.commit is not None
    assert result.commit.outcome is CommitOutcome.COMMITTED_VERIFIED
    assert result.conflicted_paths == ()
    assert result.cleanup_diagnostics == ()
    assert result.consumed_paths == (staged.resolve(), template_path.resolve())
    assert not staged.exists()
    assert not template_path.exists()
    assert not (tmp_path / commands._RECEIPT_NAME).exists()
    assert commands.validate(paths).valid


def test_add_storage_failure_preserves_staging_input(tmp_path: Path) -> None:
    paths = _workspace(tmp_path)
    staged = tmp_path / "opaque.bib"
    _staged(staged)

    def fail(phase: str) -> None:
        if phase == "workspace:before_replace:bibliography:candidate":
            raise OSError("injected")

    result = commands.add(paths, staged, fault_hook=fail)

    assert result.commit is not None
    assert result.commit.outcome is not CommitOutcome.COMMITTED_VERIFIED
    assert result.retained_paths == (staged.resolve(),)
    assert staged.exists()


def test_add_receipt_write_failure_prevents_workspace_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _workspace(tmp_path)
    staged = tmp_path / "opaque.bib"
    _staged(staged)

    before = _workspace_bytes(paths)

    def fail_receipt(_directory: Path, _receipt: commands._CleanupReceipt) -> None:
        raise OSError("receipt unavailable")

    monkeypatch.setattr(commands, "_write_receipt", fail_receipt)

    result = commands.add(paths, staged)

    assert result.commit is None
    assert result.retained_paths == (staged.resolve(),)
    assert result.consumed_paths == ()
    assert result.cleanup_diagnostics == ("could not record pending cleanup: receipt unavailable",)
    assert _workspace_bytes(paths) == before
    assert staged.exists()


def test_add_resumes_cleanup_receipt_before_new_intake(tmp_path: Path) -> None:
    paths = _workspace(tmp_path)
    staged = tmp_path / "opaque.bib"
    _staged(staged)
    commands._write_receipt(tmp_path, _pending_receipt(paths, staged))

    result = commands.add(paths, staged)

    assert result.commit is not None
    assert result.commit.outcome is CommitOutcome.COMMITTED_VERIFIED
    assert not staged.exists()
    assert not (tmp_path / commands._RECEIPT_NAME).exists()


def test_add_dry_run_preserves_pending_cleanup_receipt(tmp_path: Path) -> None:
    paths = _workspace(tmp_path)
    staged = tmp_path / "opaque.bib"
    _staged(staged)
    commands._write_receipt(tmp_path, _pending_receipt(paths, staged))

    result = commands.add(paths, staged, dry_run=True)

    assert result.added_keys == _pending_receipt(paths, staged).added_keys
    assert result.retained_paths == (staged.resolve(),)
    assert staged.exists()
    assert (tmp_path / commands._RECEIPT_NAME).exists()


def test_fabricated_candidate_receipt_cannot_delete_uncommitted_source(tmp_path: Path) -> None:
    paths = _workspace(tmp_path)
    staged = tmp_path / "opaque.bib"
    _staged(staged)
    prepared = prepare_staged_sources(((staged, staged.read_bytes()),))
    current = commands._snapshot_vector(read_workspace_snapshot(paths))
    impossible_original = commands.WorkspaceDigestVector("0" * 64, "0" * 64, "0" * 64)
    receipt = commands._CleanupReceipt(
        "0" * 32,
        prepared.files[0].keys,
        impossible_original,
        current,
        (
            commands._ReceiptItem(
                staged.name,
                prepared.files[0].sha256,
                prepared.files[0].keys,
                tuple(commands._added_entry_manifest(entry) for entry in prepared.entries),
            ),
        ),
        (staged.name,),
    )
    commands._write_receipt(tmp_path, receipt)

    result = commands.add(paths, staged)

    assert result.commit is None
    assert staged.exists()
    assert result.conflicted_paths == (tmp_path / commands._RECEIPT_NAME,)
    assert "resolution proof failed" in result.cleanup_diagnostics[0]


def test_fabricated_receipt_cannot_delete_identical_existing_source(tmp_path: Path) -> None:
    paths = _workspace(tmp_path)
    original_vector = commands._snapshot_vector(read_workspace_snapshot(paths))
    staged = tmp_path / "opaque.bib"
    _staged(staged)
    source = staged.read_bytes()
    committed = commands.add(paths, staged)
    staged.write_bytes(source)
    prepared = prepare_staged_sources(((staged, source),))
    current = commands._snapshot_vector(read_workspace_snapshot(paths))
    commands._write_receipt(
        tmp_path,
        commands._CleanupReceipt(
            "0" * 32,
            committed.added_keys,
            original_vector,
            current,
            (
                commands._ReceiptItem(
                    staged.name,
                    hashlib.sha256(source).hexdigest(),
                    committed.added_keys,
                    tuple(commands._added_entry_manifest(entry) for entry in prepared.entries),
                ),
            ),
            (staged.name,),
        ),
    )

    result = commands.add(paths, staged)

    assert result.commit is None
    assert result.conflicted_paths == (tmp_path / commands._RECEIPT_NAME,)
    assert "resolution proof failed" in result.cleanup_diagnostics[0]
    assert staged.exists()


def test_receipt_cannot_substitute_other_entry_under_legitimate_add_proof(
    tmp_path: Path,
) -> None:
    paths = _workspace(tmp_path)
    source_b = tmp_path / "b.bib"
    _staged(source_b, doi="10.1000/b")
    bytes_b = source_b.read_bytes()
    added_b = commands.add(paths, source_b)

    original_a = commands._snapshot_vector(read_workspace_snapshot(paths))
    source_a = tmp_path / "a.bib"
    _staged(source_a, doi="10.1000/a")
    commands.add(paths, source_a)
    candidate_a = commands._snapshot_vector(read_workspace_snapshot(paths))
    transaction_a = _idle_transaction_id(paths)

    source_b.write_bytes(bytes_b)
    prepared_b = prepare_staged_sources(((source_b, bytes_b),))
    forged = commands._CleanupReceipt(
        transaction_a,
        added_b.added_keys,
        original_a,
        candidate_a,
        (
            commands._ReceiptItem(
                source_b.name,
                hashlib.sha256(bytes_b).hexdigest(),
                added_b.added_keys,
                tuple(commands._added_entry_manifest(entry) for entry in prepared_b.entries),
            ),
        ),
        (source_b.name,),
    )
    commands._write_receipt(tmp_path, forged)

    result = commands.add(paths, source_b)

    assert result.commit is None
    assert result.conflicted_paths == (tmp_path / commands._RECEIPT_NAME,)
    assert "resolution proof failed" in result.cleanup_diagnostics[0]
    assert source_b.exists()


def test_candidate_receipt_source_key_mismatch_is_never_deleted(tmp_path: Path) -> None:
    paths = _workspace(tmp_path)
    original_vector = commands._snapshot_vector(read_workspace_snapshot(paths))
    first = tmp_path / "first.bib"
    _staged(first, doi="10.1000/first")
    committed = commands.add(paths, first)
    existing_key = committed.added_keys[0]
    staged = tmp_path / "opaque.bib"
    _staged(staged, doi="10.1000/different")
    current = commands._snapshot_vector(read_workspace_snapshot(paths))
    prepared = prepare_staged_sources(((staged, staged.read_bytes()),))
    source_manifest = commands._added_entry_manifest(prepared.entries[0])
    fabricated_manifest = replace(source_manifest, key=existing_key)
    commands._write_receipt(
        tmp_path,
        commands._CleanupReceipt(
            _idle_transaction_id(paths),
            (existing_key,),
            original_vector,
            current,
            (
                commands._ReceiptItem(
                    staged.name,
                    hashlib.sha256(staged.read_bytes()).hexdigest(),
                    (existing_key,),
                    (fabricated_manifest,),
                ),
            ),
            (staged.name,),
        ),
    )

    result = commands.add(paths, staged)

    assert result.commit is None
    assert result.conflicted_paths == (tmp_path / commands._RECEIPT_NAME,)
    assert staged.exists()
    assert "resolution proof failed" in result.cleanup_diagnostics[0]


def test_candidate_receipt_same_key_changed_title_is_never_deleted(tmp_path: Path) -> None:
    paths = _workspace(tmp_path)
    original_vector = commands._snapshot_vector(read_workspace_snapshot(paths))
    original = tmp_path / "original.bib"
    _staged(original)
    committed = commands.add(paths, original)
    staged = tmp_path / "altered.bib"
    staged.write_text(
        "@article{x,author={Doe, Jane},date={2024},title={Altered},doi={10.1000/work}}\n",
        encoding="utf-8",
    )
    prepared = prepare_staged_sources(((staged, staged.read_bytes()),))
    assert prepared.files[0].keys == committed.added_keys
    current = commands._snapshot_vector(read_workspace_snapshot(paths))
    commands._write_receipt(
        tmp_path,
        commands._CleanupReceipt(
            _idle_transaction_id(paths),
            committed.added_keys,
            original_vector,
            current,
            (
                commands._ReceiptItem(
                    staged.name,
                    hashlib.sha256(staged.read_bytes()).hexdigest(),
                    committed.added_keys,
                    tuple(commands._added_entry_manifest(entry) for entry in prepared.entries),
                ),
            ),
            (staged.name,),
        ),
    )

    result = commands.add(paths, staged)

    assert result.commit is None
    assert result.conflicted_paths == (tmp_path / commands._RECEIPT_NAME,)
    assert "resolution proof failed" in result.cleanup_diagnostics[0]
    assert staged.exists()

    aggregate = commands._aggregate(read_workspace_snapshot(paths))
    receipt = commands._parse_receipt(tmp_path)
    assert receipt is not None
    issue = commands._prove_receipt_item(staged, receipt.files[0], aggregate)
    assert issue is not None
    assert "committed entry content differs" in issue


def test_candidate_receipt_resumes_after_cleanup_interruption(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _workspace(tmp_path)
    staged = tmp_path / "opaque.bib"
    _staged(staged)
    original_clear = commands._clear_receipt

    def interrupt_clear(_directory: Path) -> None:
        raise OSError("interrupted")

    monkeypatch.setattr(commands, "_clear_receipt", interrupt_clear)
    first = commands.add(paths, staged)

    assert first.commit is not None
    assert first.commit.outcome is CommitOutcome.COMMITTED_VERIFIED
    assert not staged.exists()
    assert (tmp_path / commands._RECEIPT_NAME).exists()

    monkeypatch.setattr(commands, "_clear_receipt", original_clear)
    resumed = commands.add(paths, staged)

    assert resumed.added_keys == first.added_keys
    assert resumed.consumed_paths == (staged,)
    assert not (tmp_path / commands._RECEIPT_NAME).exists()


def test_source_is_reproved_immediately_before_unlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _workspace(tmp_path)
    staged = tmp_path / "opaque.bib"
    _staged(staged)
    original_prove = commands._prove_receipt_item
    mutated = False

    def prove_then_mutate(
        path: Path,
        item: commands._ReceiptItem,
        aggregate: commands.WorkspaceAggregate,
    ) -> str | None:
        nonlocal mutated
        issue = original_prove(path, item, aggregate)
        if path == staged and issue is None and not mutated:
            mutated = True
            staged.write_text(
                "@article{x,author={Doe, Jane},date={2024},title={Changed},doi={10.1000/work}}\n",
                encoding="utf-8",
            )
        return issue

    monkeypatch.setattr(commands, "_prove_receipt_item", prove_then_mutate)

    result = commands.add(paths, staged)

    assert result.commit is not None
    assert result.commit.outcome is CommitOutcome.COMMITTED_VERIFIED
    assert result.conflicted_paths == (staged.resolve(),)
    assert "drifted before unlink" in result.cleanup_diagnostics[0]
    assert staged.exists()
    assert (tmp_path / commands._RECEIPT_NAME).exists()


def test_partial_cleanup_rewrites_receipt_for_only_remaining_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _workspace(tmp_path)
    staging = tmp_path / "staging"
    staging.mkdir()
    first = staging / "a.bib"
    second = staging / "b.bib"
    _staged(first, doi="10.1000/first")
    _staged(second, doi="10.1000/second")
    original_unlink = Path.unlink

    def fail_second(path: Path, missing_ok: bool = False) -> None:
        if path == second:
            raise OSError("injected second-file cleanup failure")
        original_unlink(path, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", fail_second)
    result = commands.add(paths, staging)

    assert result.commit is not None
    assert result.commit.outcome is CommitOutcome.COMMITTED_VERIFIED
    assert not first.exists()
    assert second.exists()
    receipt = commands._parse_receipt(staging)
    assert receipt is not None
    assert tuple(item.name for item in receipt.files) == (first.name, second.name)
    assert receipt.pending_files == (second.name,)

    monkeypatch.setattr(Path, "unlink", original_unlink)
    resumed = commands.add(paths, staging)

    assert resumed.consumed_paths == (second,)
    assert not second.exists()
    assert not (staging / commands._RECEIPT_NAME).exists()


def test_add_never_consumes_workspace_artifact_as_staging(tmp_path: Path) -> None:
    paths = _workspace(tmp_path)
    before = paths.bibliography.read_bytes()

    with pytest.raises(ValueError, match="protected workspace artifact"):
        commands.add(paths, paths.bibliography)
    with pytest.raises(ValueError, match="protected workspace artifact"):
        commands.add(paths, tmp_path)

    assert paths.bibliography.read_bytes() == before


def test_add_rejects_hardlink_alias_of_workspace_artifact(tmp_path: Path) -> None:
    paths = _workspace(tmp_path)
    alias = tmp_path / "alias.bib"
    try:
        os.link(paths.bibliography, alias)
    except OSError:
        pytest.skip("hard links are unavailable")

    with pytest.raises(ValueError, match="protected workspace artifact"):
        commands.add(paths, alias)

    assert paths.bibliography.exists()


def test_add_refuses_receipt_targeting_workspace_artifact(tmp_path: Path) -> None:
    paths = _workspace(tmp_path)
    before = paths.bibliography.read_bytes()
    current = commands._snapshot_vector(read_workspace_snapshot(paths))
    other = commands.WorkspaceDigestVector("f" * 64, "f" * 64, "f" * 64)
    commands._write_receipt(
        tmp_path,
        commands._CleanupReceipt(
            "0" * 32,
            ("doe-2020-deadbeef",),
            current,
            other,
            (
                commands._ReceiptItem(
                    paths.bibliography.name,
                    hashlib.sha256(paths.bibliography.read_bytes()).hexdigest(),
                    ("doe-2020-deadbeef",),
                    (
                        commands._EntryManifest(
                            "doe-2020-deadbeef",
                            "article",
                            (),
                            "doi",
                            (("doi", "10.1000/fake"),),
                        ),
                    ),
                ),
            ),
            (paths.bibliography.name,),
        ),
    )

    result = commands.add(paths, tmp_path)

    assert paths.bibliography.read_bytes() == before
    assert (tmp_path / commands._RECEIPT_NAME).exists()
    assert result.conflicted_paths == (tmp_path / commands._RECEIPT_NAME,)
    assert "protected workspace artifact" in result.cleanup_diagnostics[0]


def test_normalize_removes_redundant_json_url_and_preserves_order_bytes(tmp_path: Path) -> None:
    arxiv = "2101.00001"
    key = _key("doe-2020", arxiv)
    paths = _workspace(
        tmp_path,
        f"@online{{{key},title={{Work}},author={{Doe, Jane}},date={{2020}},"
        f"eprint={{{arxiv}}},eprinttype={{arxiv}},"
        f"url={{https://arxiv.org/abs/{arxiv}}}}}\n",
    )
    order_before = paths.add_order.read_bytes()

    result = commands.normalize(paths, "trivial-url")

    assert result.commit is not None
    record = parse_identifier_collection(paths.identifiers.read_bytes())[key]
    assert record.identifiers == {"arxiv": arxiv}
    assert paths.add_order.read_bytes() == order_before
    assert commands.validate(paths).valid


@pytest.mark.parametrize("main_identifier", ["arxiv", "doi"])
def test_arxiv_doi_cleanup_prunes_json_without_breaking_existing_keys(
    tmp_path: Path, main_identifier: str
) -> None:
    arxiv = "2509.01002"
    doi = "10.48550/arXiv.2509.01002"
    key = _key("collins-2025", arxiv if main_identifier == "arxiv" else doi)
    paths = _workspace(
        tmp_path,
        f"@online{{{key},title={{An Introduction to Conifold Transitions}},"
        "author={Collins, Tristan C.},date={2025},eprintclass={math.DG},"
        f"eprinttype={{arxiv}},eprint={{{arxiv}}},doi={{{doi}}}}}\n",
    )
    records = parse_identifier_collection(paths.identifiers.read_bytes())
    records[key].main_identifier = main_identifier
    paths.identifiers.write_bytes(serialize_identifier_collection(records))
    before = _workspace_bytes(paths)

    preview = commands.normalize(paths, "arxiv-doi", dry_run=True)

    assert preview.changes.changed_keys == (key,)
    assert _workspace_bytes(paths) == before

    result = commands.normalize(paths, "all")

    assert result.commit is not None
    assert result.commit.outcome is CommitOutcome.COMMITTED_VERIFIED
    assert result.changes == preview.changes
    entry = BibliographyCodec.parse_bytes(paths.bibliography.read_bytes()).resolve(key)
    assert "doi" not in entry.fields_dict
    assert entry.fields_dict["eprint"].value == arxiv
    record = parse_identifier_collection(paths.identifiers.read_bytes())[key]
    if main_identifier == "arxiv":
        assert record.identifiers == {"arxiv": arxiv}
    else:
        assert paths.identifiers.read_bytes() == before[1]
        assert any("key-provenance" in diagnostic for diagnostic in result.diagnostics)
    assert paths.add_order.read_bytes() == before[2]
    assert commands.validate(paths).valid
    assert not commands.normalize(paths, "all").changes.changed


def test_normalize_cleans_json_only_redundancies_without_rewriting_bibliography(
    tmp_path: Path,
) -> None:
    arxiv = "2509.01002"
    key = _key("collins-2025", arxiv)
    paths = _workspace(
        tmp_path,
        f"@online{{{key},title={{Conifold Transitions}},author={{Collins, Tristan C.}},"
        f"date={{2025}},eprinttype={{arxiv}},eprint={{{arxiv}}}}}\n",
    )
    records = parse_identifier_collection(paths.identifiers.read_bytes())
    records[key].identifiers.update(
        doi="10.48550/arxiv.2509.01002", url="https://doi.org/10.48550/arxiv.2509.01002"
    )
    paths.identifiers.write_bytes(serialize_identifier_collection(records))
    before = _workspace_bytes(paths)

    preview = commands.normalize(paths, "all", dry_run=True)

    assert preview.changes.changed_keys == (key,)
    assert _workspace_bytes(paths) == before

    result = commands.normalize(paths, "all")

    assert result.commit is not None
    assert result.commit.outcome is CommitOutcome.COMMITTED_VERIFIED
    assert paths.bibliography.read_bytes() == before[0]
    assert paths.add_order.read_bytes() == before[2]
    assert parse_identifier_collection(paths.identifiers.read_bytes())[key].identifiers == {
        "arxiv": arxiv
    }
    assert commands.validate(paths).valid
    assert not commands.normalize(paths, "all").changes.changed


def test_reconcile_dry_run_apply_and_noop_preserve_other_artifact_bytes(tmp_path: Path) -> None:
    doi = "10.1000/work"
    url = "https://example.test/work"
    key = _key("doe-2024", doi)
    paths = _workspace(
        tmp_path,
        f"@article{{{key},author={{Doe, Jane}},date={{2024}},title={{Work}},"
        f"doi={{{doi}}},url={{{url}}}}}\n",
    )
    records = parse_identifier_collection(paths.identifiers.read_bytes())
    del records[key].identifiers["url"]
    paths.identifiers.write_bytes(serialize_identifier_collection(records))
    bibliography_before = paths.bibliography.read_bytes()
    order_before = paths.add_order.read_bytes()
    identifiers_before = paths.identifiers.read_bytes()

    preview = commands.reconcile(paths, dry_run=True)

    assert preview.commit is None
    assert [(item.kind, item.exact_value) for item in preview.additions] == [("url", url)]
    assert paths.identifiers.read_bytes() == identifiers_before

    applied = commands.reconcile(paths)

    assert applied.commit is not None
    assert applied.commit.outcome is CommitOutcome.COMMITTED_VERIFIED
    assert paths.bibliography.read_bytes() == bibliography_before
    assert paths.add_order.read_bytes() == order_before
    assert (
        parse_identifier_collection(paths.identifiers.read_bytes())[key].identifiers["url"] == url
    )

    noop = commands.reconcile(paths)
    assert noop.commit is None
    assert noop.additions == ()


def test_reconcile_collision_fails_closed_without_writing(tmp_path: Path) -> None:
    first_doi = "10.1000/first"
    second_doi = "10.1000/second"
    shared_url = "https://example.test/shared"
    first_key = _key("first-2024", first_doi)
    second_key = _key("second-2024", second_doi)
    paths = _workspace(
        tmp_path,
        f"@article{{{first_key},title={{First}},doi={{{first_doi}}},url={{{shared_url}}}}}\n"
        f"@article{{{second_key},title={{Second}},doi={{{second_doi}}}}}\n",
    )
    records = parse_identifier_collection(paths.identifiers.read_bytes())
    del records[first_key].identifiers["url"]
    records[second_key].identifiers["url"] = shared_url
    paths.identifiers.write_bytes(serialize_identifier_collection(records))
    before = _workspace_bytes(paths)

    with pytest.raises(ValueError, match="collides with record"):
        commands.reconcile(paths)

    assert _workspace_bytes(paths) == before


def test_reconcile_storage_failure_preserves_workspace_vector(tmp_path: Path) -> None:
    doi = "10.1000/work"
    key = _key("doe-2024", doi)
    paths = _workspace(
        tmp_path,
        f"@article{{{key},title={{Work}},doi={{{doi}}},url={{https://example.test}}}}\n",
    )
    records = parse_identifier_collection(paths.identifiers.read_bytes())
    del records[key].identifiers["url"]
    paths.identifiers.write_bytes(serialize_identifier_collection(records))
    before = _workspace_bytes(paths)

    def fail(phase: str) -> None:
        if phase == "workspace:before_replace:identifiers:candidate":
            raise OSError("injected")

    result = commands.reconcile(paths, fault_hook=fail)

    assert result.commit is not None
    assert result.commit.outcome is CommitOutcome.NOT_COMMITTED
    assert _workspace_bytes(paths) == before


def test_remove_and_promote_commit_all_three_artifacts(tmp_path: Path) -> None:
    arxiv = "2101.00001"
    old_key = _key("doe-2020", arxiv)
    paths = _workspace(
        tmp_path,
        f"@online{{{old_key},author={{Doe, Jane}},date={{2020}},title={{Preprint}},"
        f"eprint={{{arxiv}}},eprinttype={{arxiv}}}}\n",
    )
    payload = tmp_path / "published.bib"
    _staged(payload, doi="https://doi.org/10.1000/PAPER?x=1#top")

    promoted = commands.promote(paths, old_key, payload)

    assert promoted.commit is not None
    assert promoted.old_key == old_key
    assert promoted.canonical_doi == "10.1000/paper"
    assert old_key in promoted.aliases
    assert promoted.new_key in parse_identifier_collection(paths.identifiers.read_bytes())
    assert parse_add_order(paths.add_order.read_bytes()) == (promoted.new_key,)

    removed = commands.remove(paths, old_key)
    assert removed.commit is not None
    assert (
        BibliographyCodec.parse_bytes(paths.bibliography.read_bytes()).identity_index.canonical_keys
        == ()
    )
    assert parse_identifier_collection(paths.identifiers.read_bytes()) == {}
    assert parse_add_order(paths.add_order.read_bytes()) == ()


def test_recover_routes_to_workspace_service(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = _workspace(tmp_path)
    observed = {"bibliography": "a", "identifiers": "b", "add_order": "c"}
    monkeypatch.setattr(
        commands,
        "recover_workspace",
        lambda *_args, **_kwargs: WorkspaceRecoveryResult("already_clean", observed),
    )

    result = commands.recover(paths)

    assert result.resolution == "already_clean"
    assert result.observed == observed


def test_only_add_and_promote_call_new_doi_canonicalizer() -> None:
    source_root = Path(commands.__file__).parent
    callers: set[tuple[str, str]] = set()
    for path in source_root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for function in (
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        ):
            if any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "canonicalize_new_doi"
                for node in ast.walk(function)
            ):
                callers.add((path.name, function.name))
    assert callers == {
        ("add_entries.py", "_canonicalized_normalized_entries"),
        ("commands.py", "promote"),
    }

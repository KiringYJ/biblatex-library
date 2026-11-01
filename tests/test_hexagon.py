"""Hexagon intake keeps deterministic identity separate from bibliographic judgment."""

import hashlib
from pathlib import Path

import bibtexparser
import pytest

from biblio import commands
from biblio.add_entries import select_main_identifier
from biblio.bibliography import Bibliography, IdentityIndex
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
from biblio.identifiers import canonicalize_hexagon_identifier
from biblio.normalize.pipeline import normalize_bibliography
from biblio.storage import BibliographyCodec, WorkspacePaths
from biblio.validate import validate_bibliography

HEXAGON_EXPORT = """@misc{hexagon:2610.00311v2,
  title={On Landau--Siegel zeros},
  key={hexagon:2610.00311v2},
  howpublished={Hexagon preprint hexagon:2610.00311v2},
  year={2026},
  note={Contributors: Ben Green},
  url={https://hexagonmath.org/2610.00311v2}
}
"""
HEXAGON_ID = "2610.00311"
HEXAGON_VERSIONED_ID = HEXAGON_ID + "v2"
HEXAGON_URL = f"https://hexagonmath.org/{HEXAGON_VERSIONED_ID}"


def _bibliography(source: str) -> Bibliography:
    library = bibtexparser.parse_string(source)
    assert not library.failed_blocks
    return Bibliography(library.blocks, IdentityIndex(library.entries))


def _workspace(tmp_path: Path) -> WorkspacePaths:
    paths = WorkspacePaths(
        tmp_path / "library.bib",
        tmp_path / "identifier_collection.json",
        tmp_path / "add_order.json",
    )
    paths.bibliography.write_bytes(b"")
    paths.identifiers.write_bytes(b"{}\n")
    paths.add_order.write_bytes(b"[]\n")
    return paths


def test_export_normalizes_without_inventing_an_author_and_is_idempotent() -> None:
    bibliography = _bibliography(HEXAGON_EXPORT)

    result = normalize_bibliography(bibliography, "all")

    entry = next(iter(bibliography))
    assert entry.entry_type == "online"
    assert {field.key: str(field.value) for field in entry.fields} == {
        "title": "On Landau--Siegel zeros",
        "date": "2026",
        "note": "Contributors: Ben Green",
        "eprint": HEXAGON_ID,
        "eprinttype": "hexagon",
    }
    assert result.changes.changed_keys == ("hexagon:2610.00311v2",)
    assert not result.diagnostics
    assert not normalize_bibliography(bibliography, "all").changes.changed


@pytest.mark.parametrize("with_template", [False, True])
def test_export_template_dry_run_add_and_validation(tmp_path: Path, with_template: bool) -> None:
    paths = _workspace(tmp_path)
    staged = tmp_path / "preprint.bib"
    staged.write_text(HEXAGON_EXPORT, encoding="utf-8")
    if with_template:
        commands.template(staged)
        record = parse_identifier_collection(staged.with_suffix(".json").read_bytes())[
            "hexagon:2610.00311v2"
        ]
        assert record == IdentifierRecord("hexagon", {"hexagon": HEXAGON_ID})
    key = f"unknown-2026-{hashlib.sha256(HEXAGON_ID.encode()).hexdigest()[:8]}"

    preview = commands.add(paths, staged, dry_run=True)

    assert preview.added_keys == (key,)
    assert staged.read_text(encoding="utf-8") == HEXAGON_EXPORT
    assert paths.bibliography.read_bytes() == b""
    assert paths.identifiers.read_bytes() == b"{}\n"
    assert paths.add_order.read_bytes() == b"[]\n"

    result = commands.add(paths, staged)

    assert result.added_keys == (key,)
    assert not staged.exists()
    assert not staged.with_suffix(".json").exists()
    entry = BibliographyCodec.parse_bytes(paths.bibliography.read_bytes()).resolve(key)
    assert entry.entry_type == "online"
    assert "author" not in entry.fields_dict
    assert entry.fields_dict["note"].value == "Contributors: Ben Green"
    assert "url" not in entry.fields_dict
    assert parse_identifier_collection(paths.identifiers.read_bytes())[key] == IdentifierRecord(
        "hexagon", {"hexagon": HEXAGON_ID}
    )
    assert parse_add_order(paths.add_order.read_bytes()) == (key,)
    assert commands.validate(paths).valid
    assert not commands.normalize(paths, "all").changes.changed


@pytest.mark.parametrize("with_template", [False, True])
@pytest.mark.parametrize("class_field", ["eprintclass", "EPRINTCLASS", "primaryclass"])
def test_import_preserves_hexagon_subject_classification(
    tmp_path: Path, with_template: bool, class_field: str
) -> None:
    paths = _workspace(tmp_path)
    staged = tmp_path / "classified.bib"
    source = HEXAGON_EXPORT.replace("year={2026}", f"year={{2026}},{class_field}={{math.NT}}")
    staged.write_text(source, encoding="utf-8")
    if with_template:
        commands.template(staged)
        records = parse_identifier_collection(staged.with_suffix(".json").read_bytes())
        assert tuple(records.values()) == (IdentifierRecord("hexagon", {"hexagon": HEXAGON_ID}),)

    preview = commands.add(paths, staged, dry_run=True)

    assert staged.read_text(encoding="utf-8") == source
    assert paths.bibliography.read_bytes() == b""
    assert not preview.normalization_diagnostics

    result = commands.add(paths, staged)
    key = f"unknown-2026-{hashlib.sha256(HEXAGON_ID.encode()).hexdigest()[:8]}"
    assert result.added_keys == (key,)
    entry = BibliographyCodec.parse_bytes(paths.bibliography.read_bytes()).resolve(key)
    fields = {item.key.casefold(): str(item.value) for item in entry.fields}
    assert entry.entry_type == "online"
    assert fields["eprintclass"] == "math.NT"
    assert fields["eprint"] == HEXAGON_ID
    assert "primaryclass" not in fields
    assert "url" not in fields
    assert parse_identifier_collection(paths.identifiers.read_bytes())[key] == IdentifierRecord(
        "hexagon", {"hexagon": HEXAGON_ID}
    )
    assert commands.validate(paths).valid
    assert not commands.normalize(paths, "all").changes.changed


@pytest.mark.parametrize("action", ["all", "hexagon-fields"])
def test_conflicting_hexagon_class_aliases_preserve_the_entry(action: str) -> None:
    bibliography = _bibliography(
        "@misc{temporary,eprinttype={hexagon},eprint={2610.00311v2},"
        "primaryclass={math.NT},EPRINTCLASS={math.AG},url={https://hexagonmath.org/2610.00311v2}}"
    )
    before = BibliographyCodec.serialize(bibliography)

    result = normalize_bibliography(bibliography, action)

    assert not result.changes.changed
    assert BibliographyCodec.serialize(bibliography) == before
    assert any("manual-review" in diagnostic for diagnostic in result.diagnostics)


@pytest.mark.parametrize("has_canonical_class", [False, True])
def test_hexagon_fields_migrates_a_matching_class_alias_without_reinterpreting_it(
    has_canonical_class: bool,
) -> None:
    canonical = ",EPRINTCLASS={ math.NT }" if has_canonical_class else ""
    bibliography = _bibliography(
        "@misc{temporary,eprinttype={hexagon},eprint={2610.00311v2},"
        f"PRIMARYCLASS={{ math.NT }}{canonical}}}"
    )

    normalize_bibliography(bibliography, "hexagon-fields")

    entry = next(iter(bibliography))
    assert entry.entry_type == "online"
    fields = {item.key.casefold(): str(item.value) for item in entry.fields}
    assert fields["eprintclass"] == " math.NT "
    assert "PRIMARYCLASS" not in entry.fields_dict
    assert not normalize_bibliography(bibliography, "hexagon-fields").changes.changed


def test_reviewed_identifier_and_author_selection_remain_authoritative(tmp_path: Path) -> None:
    paths = _workspace(tmp_path)
    staged = tmp_path / "reviewed.bib"
    staged.write_text(
        HEXAGON_EXPORT.replace("year={2026}", "author={Green, Ben},year={2026}"), encoding="utf-8"
    )
    commands.template(staged)
    companion = staged.with_suffix(".json")
    records = parse_identifier_collection(companion.read_bytes())
    records["hexagon:2610.00311v2"].identifiers["url"] = HEXAGON_URL
    records["hexagon:2610.00311v2"].main_identifier = "url"
    companion.write_bytes(serialize_identifier_collection(records))

    result = commands.add(paths, staged)

    key = f"green-2026-{hashlib.sha256(HEXAGON_URL.encode()).hexdigest()[:8]}"
    assert result.added_keys == (key,)
    assert parse_identifier_collection(paths.identifiers.read_bytes())[key].main_identifier == "url"
    assert commands.validate(paths).valid


@pytest.mark.parametrize("version", ["", "v1", "v7"])
def test_revisions_share_the_same_new_identifier_and_citekey(tmp_path: Path, version: str) -> None:
    paths = _workspace(tmp_path)
    staged = tmp_path / "revision.bib"
    staged.write_text(
        HEXAGON_EXPORT.replace(HEXAGON_VERSIONED_ID, HEXAGON_ID + version), encoding="utf-8"
    )
    commands.template(staged)
    records = parse_identifier_collection(staged.with_suffix(".json").read_bytes())
    assert tuple(records.values()) == (IdentifierRecord("hexagon", {"hexagon": HEXAGON_ID}),)

    result = commands.add(paths, staged)

    assert result.added_keys == (
        f"unknown-2026-{hashlib.sha256(HEXAGON_ID.encode()).hexdigest()[:8]}",
    )
    assert commands.validate(paths).valid


def test_old_staging_companion_is_canonicalized_before_hashing(tmp_path: Path) -> None:
    paths = _workspace(tmp_path)
    staged = tmp_path / "old-template.bib"
    staged.write_text(HEXAGON_EXPORT, encoding="utf-8")
    companion = staged.with_suffix(".json")
    record = IdentifierRecord(
        "hexagon",
        {"hexagon": "HEXAGON:2610.00311v2", "url": HEXAGON_URL},
        {"hexagon": ("2610.00311v1",)},
    )
    companion.write_bytes(serialize_identifier_collection({"hexagon:2610.00311v2": record}))
    before = companion.read_bytes()

    preview = commands.add(paths, staged, dry_run=True)

    assert companion.read_bytes() == before
    assert staged.exists()
    assert any(
        delta.field == "identifiers.hexagon" and delta.after == HEXAGON_ID
        for delta in preview.changes.field_deltas
    )
    result = commands.add(paths, staged)
    key = f"unknown-2026-{hashlib.sha256(HEXAGON_ID.encode()).hexdigest()[:8]}"
    assert result.added_keys == (key,)
    assert parse_identifier_collection(paths.identifiers.read_bytes())[key] == IdentifierRecord(
        "hexagon", {"hexagon": HEXAGON_ID}
    )
    assert commands.validate(paths).valid


@pytest.mark.parametrize("has_primary", [False, True])
def test_malformed_hexagon_companions_fail_before_cleanup(
    tmp_path: Path, has_primary: bool
) -> None:
    paths = _workspace(tmp_path)
    staged = tmp_path / "malformed.bib"
    staged.write_text(HEXAGON_EXPORT, encoding="utf-8")
    record = IdentifierRecord(
        "hexagon" if has_primary else "url",
        {"hexagon": HEXAGON_ID} if has_primary else {"url": HEXAGON_URL},
        {"hexagon": () if has_primary else (HEXAGON_VERSIONED_ID,)},
    )
    companion = staged.with_suffix(".json")
    companion.write_bytes(serialize_identifier_collection({"hexagon:2610.00311v2": record}))
    before = companion.read_bytes()

    with pytest.raises(ValueError, match="Hexagon"):
        commands.add(paths, staged)

    assert staged.exists()
    assert companion.read_bytes() == before
    assert paths.bibliography.read_bytes() == b""


@pytest.mark.parametrize("changed_author", [False, True])
def test_reimporting_another_revision_cannot_create_a_duplicate_work(
    tmp_path: Path, changed_author: bool
) -> None:
    paths = _workspace(tmp_path)
    first = tmp_path / "first.bib"
    first.write_text(HEXAGON_EXPORT.replace("v2", "v1"), encoding="utf-8")
    commands.add(paths, first)
    revised = tmp_path / "revised.bib"
    source = (
        HEXAGON_EXPORT.replace("year={2026}", "author={Green, Ben},year={2026}")
        if changed_author
        else HEXAGON_EXPORT
    )
    revised.write_text(source, encoding="utf-8")
    artifacts = (paths.bibliography, paths.identifiers, paths.add_order)
    before = tuple(path.read_bytes() for path in artifacts)

    with pytest.raises(ValueError, match="duplicate canonical key|identifier 'hexagon'.*collides"):
        commands.add(paths, revised)

    assert revised.read_text(encoding="utf-8") == source
    assert tuple(path.read_bytes() for path in artifacts) == before


@pytest.mark.parametrize("same_work", [True, False])
def test_intake_checks_new_work_ids_against_legacy_versioned_inventory(
    tmp_path: Path, same_work: bool
) -> None:
    paths = _workspace(tmp_path)
    legacy = "HEXAGON:2610.00311v1"
    old_key = f"unknown-2026-{hashlib.sha256(legacy.encode()).hexdigest()[:8]}"
    paths.bibliography.write_text(
        f"@online{{{old_key},title={{Legacy}},date={{2026}},"
        f"eprinttype={{hexagon}},eprint={{{legacy}}}}}",
        encoding="utf-8",
    )
    paths.identifiers.write_bytes(
        serialize_identifier_collection({old_key: IdentifierRecord("hexagon", {"hexagon": legacy})})
    )
    paths.add_order.write_bytes(serialize_add_order((old_key,)))
    assert commands.validate(paths).valid
    staged = tmp_path / "next.bib"
    staged.write_text(
        HEXAGON_EXPORT if same_work else HEXAGON_EXPORT.replace("2610.00311", "2610.00312"),
        encoding="utf-8",
    )
    artifacts = (paths.bibliography, paths.identifiers, paths.add_order)
    before = tuple(path.read_bytes() for path in artifacts)

    if same_work:
        with pytest.raises(ValueError, match="identifier 'hexagon'.*collides"):
            commands.add(paths, staged)
        assert staged.exists()
        assert tuple(path.read_bytes() for path in artifacts) == before
    else:
        commands.add(paths, staged)
        assert commands.validate(paths).valid
        assert parse_identifier_collection(paths.identifiers.read_bytes())[
            old_key
        ] == IdentifierRecord("hexagon", {"hexagon": legacy})


@pytest.mark.parametrize("raw_export", [True, False])
def test_existing_workspace_normalization_adds_projections_without_rekeying(
    tmp_path: Path, raw_export: bool
) -> None:
    paths = _workspace(tmp_path)
    main = "url" if raw_export else "hexagon"
    exact = HEXAGON_URL if raw_export else " HEXAGON:2610.00311v2 "
    key = f"unknown-2026-{hashlib.sha256(exact.encode()).hexdigest()[:8]}"
    source = (
        HEXAGON_EXPORT.replace("@misc{hexagon:2610.00311v2,", f"@misc{{{key},")
        if raw_export
        else f"@misc{{{key},title={{X}},date={{2026}},eprinttype={{hexagon}},eprint={{{exact}}}}}"
    )
    paths.bibliography.write_text(source, encoding="utf-8")
    paths.identifiers.write_bytes(
        serialize_identifier_collection({key: IdentifierRecord(main, {main: exact})})
    )
    paths.add_order.write_bytes(serialize_add_order((key,)))
    artifacts = (paths.bibliography, paths.identifiers, paths.add_order)
    before = tuple(path.read_bytes() for path in artifacts)
    assert commands.validate(paths).valid

    preview = commands.normalize(paths, "hexagon-fields", dry_run=True)

    assert preview.changes.changed_keys == (key,)
    assert tuple(path.read_bytes() for path in artifacts) == before
    added_field = "identifiers.hexagon" if raw_export else "identifier_alternates.hexagon[0]"
    assert any(delta.field == added_field for delta in preview.changes.field_deltas)

    commands.normalize(paths, "hexagon-fields")

    record = parse_identifier_collection(paths.identifiers.read_bytes())[key]
    assert record.main_identifier == main
    assert record.identifiers[main] == exact
    assert HEXAGON_ID in record.inventory_values("hexagon")
    entry = BibliographyCodec.parse_bytes(paths.bibliography.read_bytes()).resolve(key)
    assert entry.fields_dict["eprint"].value == HEXAGON_ID
    assert "url" not in entry.fields_dict
    assert record.key_history == ()
    assert paths.add_order.read_bytes() == before[2]
    assert commands.validate(paths).valid
    assert not commands.normalize(paths, "hexagon-fields").changes.changed


def test_normalization_retains_json_only_versions_and_exact_alias_history(tmp_path: Path) -> None:
    paths = _workspace(tmp_path)
    earlier = "hexagon:2610.00311v1"
    key = f"unknown-2026-{hashlib.sha256(HEXAGON_URL.encode()).hexdigest()[:8]}"
    alias = f"unknown-2026-{hashlib.sha256(earlier.encode()).hexdigest()[:8]}"
    source = HEXAGON_EXPORT.replace("@misc{hexagon:2610.00311v2,", f"@misc{{{key},ids={{{alias}}},")
    history = (KeyHistory(alias, "hexagon", earlier), KeyHistory(key, "url", HEXAGON_URL))
    record = IdentifierRecord("url", {"url": HEXAGON_URL, "hexagon": earlier}, key_history=history)
    paths.bibliography.write_text(source, encoding="utf-8")
    paths.identifiers.write_bytes(serialize_identifier_collection({key: record}))
    paths.add_order.write_bytes(serialize_add_order((key,)))
    assert commands.validate(paths).valid

    result = commands.normalize(paths, "all")

    record = parse_identifier_collection(paths.identifiers.read_bytes())[key]
    assert record.main_identifier == "url"
    assert record.identifiers == {"url": HEXAGON_URL, "hexagon": earlier}
    assert record.identifier_alternates == {"hexagon": (HEXAGON_ID,)}
    assert record.key_history == history
    assert BibliographyCodec.parse_bytes(paths.bibliography.read_bytes()).resolve(alias).key == key
    assert any(
        delta.field == "identifier_alternates.hexagon[0]" and delta.after == HEXAGON_ID
        for delta in result.changes.field_deltas
    )
    assert commands.validate(paths).valid
    assert not commands.normalize(paths, "all").changes.changed


def test_normalization_collision_fails_before_any_workspace_write(tmp_path: Path) -> None:
    paths = _workspace(tmp_path)
    key = f"unknown-2026-{hashlib.sha256(HEXAGON_URL.encode()).hexdigest()[:8]}"
    other = f"other-2026-{hashlib.sha256(HEXAGON_ID.encode()).hexdigest()[:8]}"
    source = HEXAGON_EXPORT.replace("@misc{hexagon:2610.00311v2,", f"@misc{{{key},")
    paths.bibliography.write_text(source + f"@misc{{{other},title={{Other}}}}", encoding="utf-8")
    paths.identifiers.write_bytes(
        serialize_identifier_collection(
            {
                key: IdentifierRecord("url", {"url": HEXAGON_URL}),
                other: IdentifierRecord("hexagon", {"hexagon": HEXAGON_ID}),
            }
        )
    )
    paths.add_order.write_bytes(serialize_add_order((key, other)))
    assert commands.validate(paths).valid
    artifacts = (paths.bibliography, paths.identifiers, paths.add_order)
    before = tuple(path.read_bytes() for path in artifacts)

    with pytest.raises(ValueError, match="identifier 'hexagon'.*collides"):
        commands.normalize(paths, "all")

    assert tuple(path.read_bytes() for path in artifacts) == before


@pytest.mark.parametrize("other_id", ["2610.00311v1", "HEXAGON:2610.00311v2"])
def test_legacy_json_only_identity_retains_version_provenance(
    tmp_path: Path, other_id: str
) -> None:
    paths = _workspace(tmp_path)
    key = f"unknown-2026-{hashlib.sha256(HEXAGON_VERSIONED_ID.encode()).hexdigest()[:8]}"
    other = f"other-2026-{hashlib.sha256(other_id.encode()).hexdigest()[:8]}"
    paths.bibliography.write_text(
        f"@misc{{{key},title={{X}}}}\n@misc{{{other},title={{Y}}}}", encoding="utf-8"
    )
    paths.identifiers.write_bytes(
        serialize_identifier_collection(
            {
                key: IdentifierRecord("hexagon", {"hexagon": HEXAGON_VERSIONED_ID}),
                other: IdentifierRecord("hexagon", {"hexagon": other_id}),
            }
        )
    )
    paths.add_order.write_bytes(serialize_add_order((key, other)))

    result = commands.validate(paths)

    assert result.valid == (other_id != "HEXAGON:2610.00311v2")
    if not result.valid:
        assert any(
            "identifier 'hexagon'" in issue and "collides" in issue for issue in result.issues
        )


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("key={hexagon:2610.00311v2}", "key={hexagon:2610.00312v2}"),
        ("https://hexagonmath.org/2610.00311v2", "https://hexagonmath.org/2610.00312v2"),
        ("https://hexagonmath.org/", "https://hexagonmath.org.evil.test/"),
        ("https://hexagonmath.org/", "https://user@hexagonmath.org/"),
        ("https://hexagonmath.org/", "https://hexagonmath.org:443/"),
        ("https://hexagonmath.org/", "https://hexagonmath.org/pdf/"),
        (HEXAGON_URL, HEXAGON_URL + "?download=1"),
        (HEXAGON_URL, HEXAGON_URL + "#page=2"),
        (HEXAGON_URL, HEXAGON_URL + "/"),
        ("Hexagon preprint hexagon:2610.00311v2", "Hexagon preprint hexagon:2613.00311v2"),
        ("year={2026}", "year={2026},eprinttype={arxiv},eprint={2610.00311v2}"),
        ("year={2026}", "year={2026},eprinttype={hexagon},eprint={2610.00312v2}"),
        ("year={2026}", "year={2026},eprint={}"),
    ],
)
def test_conflicting_or_unsupported_export_metadata_is_preserved(old: str, new: str) -> None:
    bibliography = _bibliography(HEXAGON_EXPORT.replace(old, new))
    before = BibliographyCodec.serialize(bibliography)

    result = normalize_bibliography(bibliography, "hexagon-fields")

    assert BibliographyCodec.serialize(bibliography) == before
    assert not result.changes.changed
    assert any("manual-review" in diagnostic for diagnostic in result.diagnostics)


@pytest.mark.parametrize(
    "fields",
    [
        f"url={{{HEXAGON_URL}}}",
        f"key={{hexagon:{HEXAGON_ID}}}",
        f"eprint={{{HEXAGON_ID}}}",
        f"note={{Hexagon preprint hexagon:{HEXAGON_ID}}}",
    ],
)
def test_unmarked_metadata_does_not_infer_hexagon_identity(fields: str) -> None:
    bibliography = _bibliography(f"@misc{{temporary,title={{X}},{fields}}}")
    before = BibliographyCodec.serialize(bibliography)

    result = normalize_bibliography(bibliography, "hexagon-fields")

    assert not result.changes.changed
    assert BibliographyCodec.serialize(bibliography) == before
    assert "hexagon" not in identifiers_from_entry(next(iter(bibliography)))


@pytest.mark.parametrize("entry_type", ["article", "book", "inproceedings", "unpublished"])
def test_explicit_hexagon_metadata_preserves_other_entry_types(entry_type: str) -> None:
    bibliography = _bibliography(
        f"@{entry_type}{{x,eprinttype={{hexagon}},eprint={{{HEXAGON_ID}}},url={{{HEXAGON_URL}}}}}"
    )

    result = normalize_bibliography(bibliography, "hexagon-fields")

    assert next(iter(bibliography)).entry_type == entry_type
    assert result.changes.changed
    assert "url" not in next(iter(bibliography)).fields_dict


def test_raw_export_convention_does_not_reclassify_published_entries() -> None:
    bibliography = _bibliography(HEXAGON_EXPORT.replace("@misc", "@article"))
    before = BibliographyCodec.serialize(bibliography)
    assert not normalize_bibliography(bibliography, "hexagon-fields").changes.changed
    assert BibliographyCodec.serialize(bibliography) == before


def test_explicit_hexagon_uses_version_free_eprint_without_supplying_url() -> None:
    exact = " HEXAGON:2610.00311v2 "
    bibliography = _bibliography(f"@misc{{x,EPRINTTYPE={{Hexagon}},EPRINT={{{exact}}}}}")

    normalize_bibliography(bibliography, "hexagon-fields")

    entry = next(iter(bibliography))
    assert entry.entry_type == "online"
    assert entry.fields_dict["EPRINT"].value == HEXAGON_ID
    assert entry.fields_dict["EPRINTTYPE"].value == "hexagon"
    assert "url" not in entry.fields_dict
    assert identifiers_from_entry(entry) == {"hexagon": HEXAGON_ID}


@pytest.mark.parametrize("url_id", [HEXAGON_ID, HEXAGON_VERSIONED_ID, HEXAGON_ID + "v7"])
def test_trivial_url_removes_same_work_link_without_applying_version_normalization(
    url_id: str,
) -> None:
    bibliography = _bibliography(
        f"@online{{x,eprinttype={{hexagon}},eprint={{{HEXAGON_VERSIONED_ID}}},"
        f"url={{https://hexagonmath.org/{url_id}}}}}"
    )

    result = normalize_bibliography(bibliography, "trivial-url")

    entry = next(iter(bibliography))
    assert result.changes.changed
    assert "url" not in entry.fields_dict
    assert entry.fields_dict["eprint"].value == HEXAGON_VERSIONED_ID


@pytest.mark.parametrize(
    "url",
    [
        HEXAGON_URL + "?download=1",
        HEXAGON_URL + "#page=2",
        "https://hexagonmath.org/pdf/2610.00311v2",
        "https://hexagonmath.org/2610.00312",
        "https://hexagonmath.org:443/2610.00311",
        "https://user@hexagonmath.org/2610.00311",
    ],
)
def test_typed_hexagon_keeps_additional_url_information(url: str) -> None:
    bibliography = _bibliography(
        f"@online{{x,eprinttype={{hexagon}},eprint={{{HEXAGON_VERSIONED_ID}}},url={{{url}}}}}"
    )

    normalize_bibliography(bibliography, "all")

    entry = next(iter(bibliography))
    assert entry.fields_dict["eprint"].value == HEXAGON_ID
    assert entry.fields_dict["url"].value == url


@pytest.mark.parametrize(
    "alias", ["eprinttype", "archiveprefix", "archiveprefix={HEXAGON},eprinttype"]
)
def test_explicit_hexagon_marker_aliases_are_supported(alias: str) -> None:
    bibliography = _bibliography(f"@misc{{x,{alias}={{HEXAGON}},eprint={{{HEXAGON_ID}}}}}")
    result = normalize_bibliography(bibliography, "all")
    entry = next(iter(bibliography))
    assert entry.entry_type == "online"
    assert entry.fields_dict["eprinttype"].value == "hexagon"
    assert "archiveprefix" not in entry.fields_dict
    assert not result.diagnostics


def test_duplicate_field_rejection_precedes_hexagon_mutation() -> None:
    bibliography = _bibliography(HEXAGON_EXPORT + "@misc{other,url={one},URL={two}}")
    before = BibliographyCodec.serialize(bibliography)
    with pytest.raises(ValueError, match="duplicate 'url' fields"):
        normalize_bibliography(bibliography, "hexagon-fields")
    assert BibliographyCodec.serialize(bibliography) == before


def test_legacy_comparison_preserves_exact_hash_inputs_while_new_ids_drop_versions() -> None:
    exact = " HEXAGON:2610.00311v2 "
    assert identifier_equality_token("hexagon", exact) == HEXAGON_VERSIONED_ID
    assert identifier_equality_token("hexagon", "2610.00311v1") != HEXAGON_VERSIONED_ID
    assert identifier_equality_token("hexagon", "2610.00311") != HEXAGON_VERSIONED_ID
    assert canonicalize_hexagon_identifier(exact) == HEXAGON_ID
    assert canonicalize_hexagon_identifier("2610.00311v1") == HEXAGON_ID
    assert canonicalize_hexagon_identifier(HEXAGON_ID) == HEXAGON_ID
    records = {"x": IdentifierRecord("hexagon", {"hexagon": exact})}
    assert parse_identifier_collection(serialize_identifier_collection(records)) == records
    assert select_main_identifier({"hexagon": exact, "url": HEXAGON_URL}) == ("hexagon", exact)
    assert select_main_identifier({"hexagon": exact, "doi": "10.1000/paper"}) == (
        "doi",
        "10.1000/paper",
    )


@pytest.mark.parametrize(
    "value",
    [
        "",
        "2613.00311v2",
        "2600.00311",
        "2610.0031",
        "2610.00311v0",
        "2610.00311v02",
        "２６１０.00311",
    ],
)
def test_malformed_hexagon_ids_are_rejected(value: str) -> None:
    with pytest.raises(ValueError, match="Hexagon"):
        identifier_equality_token("hexagon", value)


@pytest.mark.parametrize(
    "fields",
    [
        "eprinttype={hexagon}",
        "eprinttype={hexagon},eprint={bad}",
        f"eprinttype={{hexagon}},archiveprefix={{arxiv}},eprint={{{HEXAGON_ID}}}",
        f"eprinttype={{arxiv}},archiveprefix={{hexagon}},eprint={{{HEXAGON_ID}}}",
    ],
)
def test_validation_reports_malformed_or_conflicting_hexagon_metadata(fields: str) -> None:
    bibliography = _bibliography(f"@misc{{unknown-2026-00000000,title={{X}},{fields}}}")
    result = validate_bibliography(bibliography)
    assert not result.valid
    assert any("Hexagon" in issue for issue in result.issues)

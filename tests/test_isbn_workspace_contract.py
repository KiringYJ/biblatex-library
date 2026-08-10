"""ISBN normalization contract across the coordinated workspace."""

import hashlib
from pathlib import Path

from biblio import commands
from biblio.identifier_collection import IdentifierRecord, serialize_identifier_collection
from biblio.storage import BibliographyCodec, WorkspacePaths


def _workspace(tmp_path: Path) -> tuple[WorkspacePaths, str, bytes, bytes]:
    exact_isbn10 = "0-387-97926-3"
    key = f"doe-1998-{hashlib.sha256(exact_isbn10.encode()).hexdigest()[:8]}"
    paths = WorkspacePaths(
        tmp_path / "library.bib",
        tmp_path / "identifier_collection.json",
        tmp_path / "add_order.json",
    )
    paths.bibliography.write_text(
        f"@book{{{key},title={{Geometry}},isbn={{{exact_isbn10}}}}}\n",
        encoding="utf-8",
    )
    identifier_bytes = serialize_identifier_collection(
        {key: IdentifierRecord("isbn13", {"isbn13": exact_isbn10})}
    )
    order_bytes = f'[\n  "{key}"\n]\n'.encode()
    paths.identifiers.write_bytes(identifier_bytes)
    paths.add_order.write_bytes(order_bytes)
    return paths, key, identifier_bytes, order_bytes


def test_isbn10_normalization_dry_run_preserves_all_workspace_bytes(tmp_path: Path) -> None:
    paths, key, identifier_bytes, order_bytes = _workspace(tmp_path)
    bibliography_bytes = paths.bibliography.read_bytes()

    result = commands.normalize(paths, "isbn", dry_run=True)

    assert result.changes.changed_keys == (key,)
    assert paths.bibliography.read_bytes() == bibliography_bytes
    assert paths.identifiers.read_bytes() == identifier_bytes
    assert paths.add_order.read_bytes() == order_bytes


def test_isbn10_normalization_apply_preserves_exact_json_and_hash_provenance(
    tmp_path: Path,
) -> None:
    paths, key, identifier_bytes, order_bytes = _workspace(tmp_path)

    result = commands.normalize(paths, "isbn")

    assert result.commit is not None
    bibliography = BibliographyCodec.parse_bytes(paths.bibliography.read_bytes())
    assert bibliography.resolve(key).fields_dict["isbn"].value == "978-0-387-97926-7"
    assert paths.identifiers.read_bytes() == identifier_bytes
    assert paths.add_order.read_bytes() == order_bytes
    assert commands.validate(paths).valid

"""Tests for pure hard-removal lifecycle behavior."""

from pathlib import Path

import bibtexparser
import pytest

from biblio.bibliography import Bibliography, IdentityIndex
from biblio.lifecycle import remove


def _bibliography(tmp_path: Path) -> Bibliography:
    source = tmp_path / "library.bib"
    source.write_text(
        """@article{First, title={First}}
@comment{between}
@article{Canonical, title={Remove}, ids={Old, Older}}
@book{Last, title={Last}}
""",
        encoding="utf-8",
    )
    library = bibtexparser.parse_file(source)
    assert not library.failed_blocks
    return Bibliography(library.blocks, IdentityIndex(library.entries))


@pytest.mark.parametrize("identity", ["Canonical", "Old"])
def test_remove_resolves_canonical_or_alias_and_removes_complete_identity_set(
    tmp_path: Path, identity: str
) -> None:
    bibliography = _bibliography(tmp_path)
    comment = bibliography.blocks[1]

    result = remove(bibliography, identity)

    assert result.canonical_key == "Canonical"
    assert result.aliases == ("Old", "Older")
    assert [entry.key for entry in bibliography] == ["First", "Last"]
    assert result.changes.changed_keys == ("Canonical",)
    assert result.changes.alias_deltas[0].removed == ("Old", "Older")
    assert result.changes.order_delta is not None
    assert result.changes.order_delta.before == ("First", "Canonical", "Last")
    assert result.changes.order_delta.after == ("First", "Last")
    assert bibliography.blocks[1] is comment
    for removed_identity in ("Canonical", "Old", "Older"):
        with pytest.raises(KeyError, match=removed_identity):
            bibliography.resolve(removed_identity)


def test_remove_missing_identity_leaves_bibliography_unchanged(tmp_path: Path) -> None:
    bibliography = _bibliography(tmp_path)
    blocks_before = bibliography.blocks

    with pytest.raises(KeyError, match="Missing"):
        remove(bibliography, "Missing")

    assert bibliography.blocks == blocks_before

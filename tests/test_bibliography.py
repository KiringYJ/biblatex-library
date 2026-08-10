"""Tests for the ordered bibliography domain aggregate."""

from pathlib import Path

import bibtexparser
import pytest

from biblio.bibliography import Bibliography, IdentityIndex


def _parse(tmp_path: Path, source: str) -> bibtexparser.Library:
    bib_path = tmp_path / "source.bib"
    bib_path.write_text(source, encoding="utf-8")
    library = bibtexparser.parse_file(bib_path)
    assert not library.failed_blocks
    return library


def test_aggregate_preserves_blocks_entry_order_and_exact_field_values(tmp_path: Path) -> None:
    library = _parse(
        tmp_path,
        """@comment{keep me}
@article{First,
  title = {Exact {Value}},
  doi = {HTTPS://DOI.ORG/10.1000/ABC},
  ids = {OldFirst, OlderFirst},
}
@book{Second,
  title = {Second},
}
""",
    )
    index = IdentityIndex(library.entries)

    bibliography = Bibliography(library.blocks, index)

    assert bibliography.blocks == tuple(library.blocks)
    assert [entry.key for entry in bibliography] == ["First", "Second"]
    assert bibliography.resolve("First") is bibliography.resolve("OldFirst")
    assert bibliography.aliases_for("OlderFirst") == ("OldFirst", "OlderFirst")
    assert bibliography.resolve("First").fields_dict["doi"].value == ("HTTPS://DOI.ORG/10.1000/ABC")


def test_replace_append_and_delete_preserve_unaffected_positions(tmp_path: Path) -> None:
    original = _parse(
        tmp_path,
        """@article{First, title = {First}}
@comment{between}
@article{Second, title = {Second}, ids = {OldSecond}}
""",
    )
    replacement = _parse(
        tmp_path,
        """@article{Published, title = {Published}, ids = {Second, OldSecond}}
""",
    ).entries[0]
    appended = _parse(tmp_path, "@book{Third, title = {Third}}\n").entries[0]
    bibliography = Bibliography(original.blocks, IdentityIndex(original.entries))

    removed = bibliography.replace("OldSecond", replacement)
    bibliography.append(appended)

    assert removed.key == "Second"
    assert [entry.key for entry in bibliography] == ["First", "Published", "Third"]
    assert bibliography.resolve("Second") is replacement
    assert bibliography.blocks[1] == original.blocks[1]

    deleted = bibliography.delete("OldSecond")

    assert deleted is replacement
    assert [entry.key for entry in bibliography] == ["First", "Third"]
    assert bibliography.blocks[1] == original.blocks[1]
    with pytest.raises(KeyError, match="OldSecond"):
        bibliography.resolve("OldSecond")


@pytest.mark.parametrize(
    ("source", "message"),
    [
        (
            "@article{First, ids={Second}}\n@article{Second, title={Two}}\n",
            "identity 'Second' is both a canonical key and an alias",
        ),
        (
            "@article{First, ids={Shared}}\n@article{Second, ids={Shared}}\n",
            "alias 'Shared' belongs to both 'First' and 'Second'",
        ),
        (
            "@article{First, ids={Same, Same}}\n",
            "duplicate alias 'Same' for canonical key 'First'",
        ),
        (
            "@article{First, ids={Valid, }}\n",
            "empty alias for canonical key 'First'",
        ),
    ],
)
def test_identity_collisions_fail_deterministically(
    tmp_path: Path, source: str, message: str
) -> None:
    library = _parse(tmp_path, source)

    with pytest.raises(ValueError, match=message):
        IdentityIndex(library.entries)


def test_duplicate_canonical_keys_fail_deterministically(tmp_path: Path) -> None:
    entry = _parse(tmp_path, "@article{Same, title={One}}\n").entries[0]

    with pytest.raises(ValueError, match="duplicate canonical key 'Same'"):
        IdentityIndex((entry, entry))


def test_alias_matching_is_exact_case_sensitive(tmp_path: Path) -> None:
    library = _parse(tmp_path, "@article{Canonical, ids={RetiredKey}}\n")
    index = IdentityIndex(library.entries)

    assert index.resolve("RetiredKey").key == "Canonical"
    with pytest.raises(KeyError, match="retiredkey"):
        index.resolve("retiredkey")


def test_aggregate_rejects_an_index_built_for_different_entries(tmp_path: Path) -> None:
    first = _parse(tmp_path, "@article{First, title={First}}\n")
    second = _parse(tmp_path, "@article{Second, title={Second}}\n")

    with pytest.raises(ValueError, match="identity index does not match bibliography entries"):
        Bibliography(first.blocks, IdentityIndex(second.entries))

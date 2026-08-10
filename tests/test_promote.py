"""Tests for pure arXiv-to-publication lifecycle behavior."""

import hashlib
from pathlib import Path

import bibtexparser
import pytest
from bibtexparser.model import Entry

from biblio.bibliography import Bibliography, IdentityIndex
from biblio.lifecycle import promote


def _parse(tmp_path: Path, source: str, name: str = "source.bib") -> bibtexparser.Library:
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    library = bibtexparser.parse_file(path)
    assert not library.failed_blocks
    return library


def _bibliography(tmp_path: Path, extra: str = "") -> Bibliography:
    library = _parse(
        tmp_path,
        f"""@book{{First, title={{First}}}}
@comment{{between}}
@online{{preprint-2020-deadbeef,
  author = {{Doe, Jane}},
  title = {{Preprint}},
  date = {{2020-01}},
  eprint = {{2101.12345v2}},
  eprinttype = {{arxiv}},
  eprintclass = {{math.AG}},
  ids = {{very-old-key}},
}}
{extra}@book{{Last, title={{Last}}}}
""",
    )
    return Bibliography(library.blocks, IdentityIndex(library.entries))


def _published(tmp_path: Path, fields: str = "") -> Entry:
    return _parse(
        tmp_path,
        f"""@article{{payload,
  author = {{Doe, Jane}},
  title = {{Published title}},
  date = {{2024}},
  journaltitle = {{Journal}},
  doi = {{10.1000/published}},
  {fields}
}}
""",
        "published.bib",
    ).entries[0]


def test_promote_replaces_in_place_preserves_arxiv_and_accumulates_aliases(
    tmp_path: Path,
) -> None:
    bibliography = _bibliography(tmp_path)
    comment = bibliography.blocks[1]
    expected_hash = hashlib.sha256(b"10.1000/published").hexdigest()[:8]

    result = promote(
        bibliography,
        "very-old-key",
        _published(tmp_path),
        "10.1000/published",
        stripped_doi_query=True,
        stripped_doi_fragment=True,
    )

    expected_key = f"doe-2024-{expected_hash}"
    assert result.old_key == "preprint-2020-deadbeef"
    assert result.new_key == expected_key
    assert result.aliases == ("preprint-2020-deadbeef", "very-old-key")
    assert result.canonical_doi == "10.1000/published"
    assert result.stripped_doi_query
    assert result.stripped_doi_fragment
    assert [entry.key for entry in bibliography] == ["First", expected_key, "Last"]
    assert bibliography.blocks[1] is comment
    promoted = bibliography.resolve("preprint-2020-deadbeef")
    assert promoted is bibliography.resolve("very-old-key")
    assert promoted.fields_dict["ids"].value == "preprint-2020-deadbeef, very-old-key"
    assert promoted.fields_dict["doi"].value == "10.1000/published"
    assert promoted.fields_dict["eprint"].value == "2101.12345v2"
    assert promoted.fields_dict["eprinttype"].value == "arxiv"
    assert promoted.fields_dict["eprintclass"].value == "math.AG"
    assert result.changes.order_delta is not None
    assert result.changes.order_delta.before == ("First", "preprint-2020-deadbeef", "Last")
    assert result.changes.order_delta.after == ("First", expected_key, "Last")


def test_promote_uses_valid_payload_arxiv_updates(tmp_path: Path) -> None:
    bibliography = _bibliography(tmp_path)
    published = _published(
        tmp_path,
        "eprint={2101.12345v3}, eprinttype={arxiv}, eprintclass={math.DG},",
    )

    result = promote(bibliography, "preprint-2020-deadbeef", published, "10.1000/published")

    promoted = bibliography.resolve(result.new_key)
    assert promoted.fields_dict["eprint"].value == "2101.12345v3"
    assert promoted.fields_dict["eprinttype"].value == "arxiv"
    assert promoted.fields_dict["eprintclass"].value == "math.DG"


def test_promote_rejects_matching_derived_arxiv_doi_without_mutation(tmp_path: Path) -> None:
    bibliography = _bibliography(tmp_path)
    blocks_before = bibliography.blocks

    with pytest.raises(ValueError, match="matching derived arXiv DOI"):
        promote(
            bibliography,
            "preprint-2020-deadbeef",
            _published(tmp_path),
            "10.48550/arxiv.2101.12345v2",
        )

    assert bibliography.blocks == blocks_before


def test_promote_rejects_derived_doi_matching_payload_eprint_update(tmp_path: Path) -> None:
    bibliography = _bibliography(tmp_path)
    published = _parse(
        tmp_path,
        """@article{payload,
  author={Doe, Jane},
  date={2024},
  doi={10.48550/arxiv.2202.54321},
  eprint={2202.54321},
  eprinttype={arxiv},
}
""",
        "derived-published.bib",
    ).entries[0]
    blocks_before = bibliography.blocks

    with pytest.raises(ValueError, match="matching derived arXiv DOI"):
        promote(
            bibliography,
            "preprint-2020-deadbeef",
            published,
            "10.48550/arxiv.2202.54321",
        )

    assert bibliography.blocks == blocks_before


def test_promote_rejects_existing_canonical_doi_without_mutation(tmp_path: Path) -> None:
    bibliography = _bibliography(
        tmp_path,
        extra="@article{Other, title={Other}, doi={HTTPS://DOI.ORG/10.1000/PUBLISHED}}\n",
    )
    blocks_before = bibliography.blocks

    with pytest.raises(ValueError, match="already belongs to 'Other'"):
        promote(
            bibliography,
            "preprint-2020-deadbeef",
            _published(tmp_path),
            "10.1000/published",
        )

    assert bibliography.blocks == blocks_before


def test_promote_rejects_new_key_namespace_collision(tmp_path: Path) -> None:
    expected_hash = hashlib.sha256(b"10.1000/published").hexdigest()[:8]
    colliding_key = f"doe-2024-{expected_hash}"
    bibliography = _bibliography(
        tmp_path,
        extra=f"@article{{{colliding_key}, title={{Collision}}}}\n",
    )
    blocks_before = bibliography.blocks

    with pytest.raises(ValueError, match="duplicate canonical key"):
        promote(
            bibliography,
            "preprint-2020-deadbeef",
            _published(tmp_path),
            "10.1000/published",
        )

    assert bibliography.blocks == blocks_before


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        (
            "doi={10.1000/not-canonical},",
            "must equal the command-supplied canonical DOI",
        ),
        (
            "ids={injected},",
            "must not supply ids aliases",
        ),
        (
            "eprinttype={zenodo},",
            "requires eprinttype=arxiv",
        ),
    ],
)
def test_promote_rejects_invalid_validated_payload_contract_without_mutation(
    tmp_path: Path, fields: str, message: str
) -> None:
    bibliography = _bibliography(tmp_path)
    blocks_before = bibliography.blocks
    published = _parse(
        tmp_path,
        f"@article{{payload, {fields}}}\n",
        "invalid-published.bib",
    ).entries[0]

    with pytest.raises(ValueError, match=message):
        promote(bibliography, "preprint-2020-deadbeef", published, "10.1000/published")

    assert bibliography.blocks == blocks_before


def test_promote_requires_arxiv_source_record(tmp_path: Path) -> None:
    library = _parse(tmp_path, "@online{plain, author={Doe, Jane}, date={2020}}\n")
    bibliography = Bibliography(library.blocks, IdentityIndex(library.entries))

    with pytest.raises(ValueError, match="is not an arXiv record"):
        promote(bibliography, "plain", _published(tmp_path), "10.1000/published")

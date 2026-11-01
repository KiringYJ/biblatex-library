"""Tests for pure preprint-to-publication lifecycle behavior."""

import hashlib
from copy import deepcopy
from pathlib import Path

import bibtexparser
import pytest
from bibtexparser.model import Entry

from biblio.bibliography import Bibliography, IdentityIndex
from biblio.identifier_collection import IdentifierRecord, KeyHistory
from biblio.lifecycle import promote, promote_in_workspace
from biblio.workspace import WorkspaceAggregate


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


def _hexagon_bibliography(
    tmp_path: Path, fields: str = "", *, exact: str = "hexagon:2610.00311v2"
) -> Bibliography:
    suffix = hashlib.sha256(exact.encode()).hexdigest()[:8]
    library = _parse(
        tmp_path,
        f"@online{{unknown-2026-{suffix},title={{Preprint}},date={{2026}},"
        f"eprint={{{exact}}},eprinttype={{hexagon}},"
        f"url={{https://hexagonmath.org/2610.00311v2}},{fields}}}",
    )
    return Bibliography(library.blocks, IdentityIndex(library.entries))


def test_hexagon_workspace_promotion_preserves_exact_identity_and_order(tmp_path: Path) -> None:
    bibliography = _hexagon_bibliography(tmp_path, "eprintclass={math.NT},")
    old_key = tuple(bibliography)[0].key
    exact = "hexagon:2610.00311v2"
    url = "https://hexagonmath.org/2610.00311v2"
    aggregate = WorkspaceAggregate(
        bibliography,
        {old_key: IdentifierRecord("hexagon", {"hexagon": exact, "url": url})},
        (old_key,),
    )
    result = promote_in_workspace(aggregate, old_key, _published(tmp_path), "10.1000/published")

    promoted = aggregate.bibliography.resolve(old_key)
    assert promoted.entry_type == "article"
    assert promoted.fields_dict["eprint"].value == "2610.00311"
    assert promoted.fields_dict["eprinttype"].value == "hexagon"
    assert promoted.fields_dict["eprintclass"].value == "math.NT"
    assert "url" not in promoted.fields_dict
    assert aggregate.add_order == (result.new_key,)
    record = aggregate.identifiers[result.new_key]
    assert record.main_identifier == "doi"
    assert record.identifiers == {"hexagon": exact, "url": url, "doi": "10.1000/published"}
    assert record.identifier_alternates == {"hexagon": ("2610.00311",)}
    assert old_key.endswith(hashlib.sha256(exact.encode()).hexdigest()[:8])
    assert record.key_history == (
        KeyHistory(old_key, "hexagon", exact),
        KeyHistory(result.new_key, "doi", "10.1000/published"),
    )
    aggregate.validate()


def test_hexagon_promotion_accepts_same_provider_payload_updates(tmp_path: Path) -> None:
    bibliography = _hexagon_bibliography(tmp_path)
    old_key = tuple(bibliography)[0].key
    result = promote(
        bibliography,
        old_key,
        _published(tmp_path, "eprint={2610.00311v3},eprinttype={Hexagon},eprintclass={math.NT},"),
        "10.1000/published",
    )
    promoted = bibliography.resolve(result.new_key)
    assert promoted.fields_dict["eprint"].value == "2610.00311"
    assert promoted.fields_dict["eprinttype"].value == "hexagon"
    assert promoted.fields_dict["eprintclass"].value == "math.NT"
    assert "url" not in promoted.fields_dict


@pytest.mark.parametrize(
    "url",
    [
        "https://example.test/paper",
        "https://hexagonmath.org/2610.00312",
        "https://hexagonmath.org/2610.00311?download=1",
        "https://hexagonmath.org/2610.00311.pdf",
    ],
)
def test_hexagon_promotion_preserves_nonmatching_payload_url(tmp_path: Path, url: str) -> None:
    bibliography = _hexagon_bibliography(tmp_path)
    old_key = tuple(bibliography)[0].key
    result = promote(
        bibliography,
        old_key,
        _published(tmp_path, f"url={{{url}}},"),
        "10.1000/published",
    )
    promoted = bibliography.resolve(result.new_key)
    assert promoted.fields_dict["url"].value == url
    assert promoted.fields_dict["eprint"].value == "2610.00311"


@pytest.mark.parametrize(
    ("source_provider", "fields", "message"),
    [
        ("hexagon", "eprinttype={arxiv},", "requires eprinttype=hexagon"),
        ("arxiv", "eprinttype={hexagon},", "requires eprinttype=arxiv"),
        ("hexagon", "eprint={2613.00311v2},", "Hexagon YYMM"),
        ("hexagon", "eprint={},", "requires a nonempty eprint"),
        ("hexagon", "archiveprefix={arxiv},", "conflicting archiveprefix"),
        ("arxiv", "archiveprefix={hexagon},", "conflicting archiveprefix"),
        (
            "hexagon",
            "primaryclass={math.NT},eprintclass={math.AG},",
            "conflicting primaryclass",
        ),
    ],
)
def test_promotion_rejects_invalid_preprint_payload_without_mutation(
    tmp_path: Path, source_provider: str, fields: str, message: str
) -> None:
    bibliography = (
        _hexagon_bibliography(tmp_path) if source_provider == "hexagon" else _bibliography(tmp_path)
    )
    current = next(entry for entry in bibliography if "eprint" in entry.fields_dict)
    before = deepcopy(bibliography.blocks)
    with pytest.raises(ValueError, match=message):
        promote(bibliography, current.key, _published(tmp_path, fields), "10.1000/published")
    assert bibliography.blocks == before


@pytest.mark.parametrize(
    ("fields", "exact"),
    [
        ("archiveprefix={arxiv},", "2610.00311v2"),
        ("eprintclass={math.NT},primaryclass={math.AG},", "2610.00311v2"),
        ("", "2613.00311v2"),
        ("", "2610.00311v0"),
        ("", ""),
    ],
)
def test_hexagon_promotion_rejects_invalid_source_without_mutation(
    tmp_path: Path, fields: str, exact: str
) -> None:
    bibliography = _hexagon_bibliography(tmp_path, fields, exact=exact)
    before = deepcopy(bibliography.blocks)
    with pytest.raises(ValueError):
        promote(bibliography, tuple(bibliography)[0].key, _published(tmp_path), "10.1000/published")
    assert bibliography.blocks == before

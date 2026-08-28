"""Normalization must not infer bibliographic meaning or repair unknown syntax."""

import bibtexparser
import pytest

from biblio import cli
from biblio.bibliography import Bibliography, IdentityIndex
from biblio.normalize.pipeline import NORMALIZATION_ACTIONS, normalize_bibliography

RETIRED_ACTIONS = ("publisher-location",)


def _bibliography(source: str) -> Bibliography:
    library = bibtexparser.parse_string(source)
    assert not library.failed_blocks
    return Bibliography(library.blocks, IdentityIndex(library.entries))


def _snapshot(bibliography: Bibliography) -> tuple[tuple[str, tuple[tuple[str, str], ...]], ...]:
    return tuple(
        (entry.entry_type, tuple((field.key, str(field.value)) for field in entry.fields))
        for entry in bibliography
    )


def test_only_bounded_representation_actions_are_registered() -> None:
    assert NORMALIZATION_ACTIONS == (
        "year-to-date",
        "eprint-fields",
        "latex-accents",
        "name-spacing",
        "journal-fields",
        "book-pagination",
        "isbn",
        "trivial-url",
    )


@pytest.mark.parametrize("action", RETIRED_ACTIONS)
def test_retired_actions_fail_without_mutating(action: str) -> None:
    bibliography = _bibliography("@book{one,year={2020},publisher={Springer, Cham}}")
    before = _snapshot(bibliography)

    with pytest.raises(ValueError, match="unknown normalization action"):
        normalize_bibliography(bibliography, action)

    assert _snapshot(bibliography) == before


@pytest.mark.parametrize("action", RETIRED_ACTIONS)
def test_cli_rejects_retired_actions(action: str) -> None:
    with pytest.raises(SystemExit) as raised:
        cli.create_parser().parse_args(["normalize", action])

    assert raised.value.code == 2


@pytest.mark.parametrize(
    "source",
    [
        "@book{one,publisher={Springer, Cham}}",
        "@book{one,publisher={{Press, Inc.}}}",
        "@article{one,journal={Journal of Tests},shortjournal={Journal of Tests}}",
        "@article{one,journal={J. Tests},fjournal={Journal of Tests}}",
        "@article{one,journal={J. Tests},fjournal={Journal of Tests},journaltitle={Other}}",
        "@book{one,pages={42}}",
        "@book{one,pages={xiv+557},pagetotal={557}}",
        r"@book{one,author={Doe\ , Jane}}",
        r"@book{one,author={{Research , Development}}}",
        r"@book{one,title={\LaTeX and \textit{É}}}",
        r"@book{one,mrreviewer={Victor\ Mikhailovich}}",
        "@misc{one,eprinttype={arxiv}}",
        "@article{one,eprinttype={arxiv},eprint={2602.21791}}",
        "@book{one,year={2020},month={12}}",
        "@book{one,year={2020},MONTH={12}}",
        "@book{one,year={2020},DATE={2021}}",
        "@book{one,year={forthcoming}}",
        "@book{one,year={２０２０}}",
        "@book{one,year={20}}",
        "@book{one,isbn={ISBN 0-387-97926-3}}",
        "@book{one,isbn={0-387-97926-3 (hardback)}}",
        "@book{one,isbn={0-387-97926-3, invalid}}",
        "@book{one,isbn={0-387-97926-3,}}",
        "@book{one,isbn={0-387-97926-3, 9780387979268}}",
        "@book{one,isbn={9780387979267 (hardback), 9780387979267 (paperback)}}",
    ],
)
def test_all_preserves_values_outside_its_contract(source: str) -> None:
    bibliography = _bibliography(source)
    before = _snapshot(bibliography)

    result = normalize_bibliography(bibliography, "all")

    assert _snapshot(bibliography) == before
    assert not result.changes.changed


@pytest.mark.parametrize(
    "url",
    [
        "https://arxiv.org/abs/2602.21791?download=1",
        "https://arxiv.org/abs/2602.21791#page=12",
        "https://arxiv.org:8443/abs/2602.21791",
        "https://user@arxiv.org/abs/2602.21791",
        "https://arxiv.org/pdf/2602.21791",
        "https://arxiv.org/pdf/2602.21791.pdf",
        "https://arxiv.org/ABS/2602.21791",
        "https://arxiv.org/abs/2602.21791/",
        "https://arxiv.org/abs/2602.21791v2",
        "https://doi.org/10.1000/work/",
        "https://doi.org/10.1000/work?download=1",
        "https://doi.org/10.1000/work#part",
    ],
)
def test_identifier_equivalence_does_not_erase_url_information(url: str) -> None:
    bibliography = _bibliography(
        "@online{one,eprinttype={arxiv},eprint={2602.21791},doi={10.1000/work},"
        f"url={{{url}}}}}"
    )
    before = _snapshot(bibliography)

    result = normalize_bibliography(bibliography, "all")

    assert _snapshot(bibliography) == before
    assert not result.changes.changed


def test_eprint_type_conflict_preserves_the_entire_alias_namespace() -> None:
    bibliography = _bibliography(
        "@misc{one,archiveprefix={arXiv},EPRINTTYPE={HAL},primaryclass={math.AG}}"
    )
    before = _snapshot(bibliography)

    result = normalize_bibliography(bibliography, "all")

    assert _snapshot(bibliography) == before
    assert result.diagnostics == (
        "eprint-fields:manual-review:one:archiveprefix->eprinttype:conflict",
    )


def test_duplicate_field_preflight_precedes_every_mutation() -> None:
    bibliography = _bibliography(
        "@book{first,year={2020}}\n@book{second,isbn={0387979263},ISBN={038797430X}}"
    )
    before = _snapshot(bibliography)

    with pytest.raises(ValueError, match="duplicate 'isbn' fields"):
        normalize_bibliography(bibliography, "all")

    assert _snapshot(bibliography) == before


def test_case_insensitive_fields_use_the_same_safe_rules() -> None:
    bibliography = _bibliography(
        "@misc{one,YEAR={2020},ARCHIVEPREFIX={arXiv},PRIMARYCLASS={math.AG},"
        "EPRINT={2602.21791},ISBN={0387979263},URL={https://doi.org/10.1000/work},"
        "DOI={10.1000/work}}"
    )

    first = normalize_bibliography(bibliography, "all")
    entry = bibliography.resolve("one")
    values = {field.key.casefold(): str(field.value) for field in entry.fields}
    second = normalize_bibliography(bibliography, "all")

    assert values == {
        "date": "2020",
        "eprinttype": "arxiv",
        "eprintclass": "math.AG",
        "eprint": "2602.21791",
        "isbn": "9780387979267",
        "doi": "10.1000/work",
    }
    assert entry.entry_type == "online"
    assert first.changes.changed
    assert not second.changes.changed


def test_all_restores_text_and_mr_pair_normalization_without_corruption() -> None:
    bibliography = _bibliography(
        r"""@article{one,
  author = {Macr\`\i , Emanuele},
  title = {\LaTeX and \textbf{\"O} and \textit{É}},
  journal = {Jos\'e},
  fjournal = {Journal of Jos\'e},
  shortjournal = {José},
  journaltitle = {Journal of José},
  doi = {10.1000/Jos\'e},
  publisher = {Springer, Cham},
  pages = {42},
  mrclass = {53C}
}"""
    )

    first = normalize_bibliography(bibliography, "all")
    fields = bibliography.resolve("one").fields_dict

    assert fields["author"].value == "Macrì, Emanuele"
    assert fields["title"].value == r"\LaTeX and \textbf{Ö} and \textit{É}"
    assert fields["shortjournal"].value == "José"
    assert fields["journaltitle"].value == "Journal of José"
    assert "journal" not in fields and "fjournal" not in fields
    assert fields["doi"].value == r"10.1000/Jos\'e"
    assert fields["publisher"].value == "Springer, Cham"
    assert fields["pages"].value == "42"
    assert first.changes.changed
    assert not normalize_bibliography(bibliography, "all").changes.changed


def test_all_requires_mr_metadata_for_both_source_conventions() -> None:
    bibliography = _bibliography(
        "@article{markedjournal,journal={Short},fjournal={Full},MRCLASS={53C}}"
        "@article{plainjournal,journal={Short},fjournal={Full}}"
        "@book{markedbook,pages={xiv+557},mrreviewer={Reviewer}}"
        "@book{plainbook,pages={xiv+557}}"
    )

    result = normalize_bibliography(bibliography, "all")

    assert result.changes.changed_keys == ("markedjournal", "markedbook")
    assert bibliography.resolve("markedjournal").fields_dict["shortjournal"].value == "Short"
    assert bibliography.resolve("plainjournal").fields_dict["journal"].value == "Short"
    assert bibliography.resolve("markedbook").fields_dict["pagetotal"].value == "xiv+557"
    assert bibliography.resolve("plainbook").fields_dict["pages"].value == "xiv+557"
    assert not normalize_bibliography(bibliography, "all").changes.changed

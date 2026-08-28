"""MR-sensitive normalization uses explicit local metadata, not inferred provenance."""

import bibtexparser
import pytest
from bibtexparser.model import Entry

from biblio.normalize.mr import MR_FIELDS, has_mr_metadata


def _entry(fields: str) -> Entry:
    library = bibtexparser.parse_string(f"@article{{MR123456,{fields}}}")
    assert not library.failed_blocks
    return library.entries[0]


def test_marker_names_are_an_exact_closed_set() -> None:
    assert MR_FIELDS == frozenset({"mrnumber", "mrclass", "mrreviewer"})


@pytest.mark.parametrize(
    "name", ["mrnumber", "mrclass", "mrreviewer", "MRNUMBER", "MRCLASS", "MRREVIEWER"]
)
def test_nonempty_exact_markers_are_recognized_without_rewriting(name: str) -> None:
    value = "  unverified local marker  "
    entry = _entry(f"{name}={{{value}}}")
    before = tuple((field.key, field.value) for field in entry.fields)
    assert has_mr_metadata(entry)
    assert tuple((field.key, field.value) for field in entry.fields) == before


@pytest.mark.parametrize("name", ["mrnumber", "mrclass", "mrreviewer"])
@pytest.mark.parametrize("value", ["", " ", "\t\n", "\u2003"])
def test_blank_markers_do_not_qualify(name: str, value: str) -> None:
    assert not has_mr_metadata(_entry(f"{name}={{{value}}}"))


@pytest.mark.parametrize(
    "fields",
    [
        "title={MR123456}",
        "mri={123456}",
        "mrsource={MathSciNet}",
        "mrnumber_extra={123456}",
        "journal={J. Tests},fjournal={Journal of Tests}",
        "publisher={American Mathematical Society}",
        "url={https://mathscinet.ams.org/mathscinet-getitem?mr=123456}",
        "ids={MR123456}",
    ],
)
def test_other_metadata_and_citekeys_do_not_establish_the_marker(fields: str) -> None:
    assert not has_mr_metadata(_entry(fields))


def test_one_nonempty_marker_is_enough_among_blank_markers() -> None:
    assert has_mr_metadata(_entry("mrnumber={},MRCLASS={ },mrreviewer={Reviewer}"))

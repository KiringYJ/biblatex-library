"""Check that text normalization preserves Biber's name and list interpretation."""

import re
import shutil
import subprocess
from pathlib import Path

import bibtexparser
import pytest

from biblio.bibliography import Bibliography, IdentityIndex
from biblio.normalize.accents import normalize_latex_accents


@pytest.mark.integration
def test_normalization_preserves_biber_name_and_list_structure(tmp_path: Path) -> None:
    biber = shutil.which("biber")
    if biber is None:
        pytest.skip("integration tool is not installed: biber")
        raise AssertionError("pytest.skip unexpectedly returned")
    cases = (
        ("author", r"\AE John"),
        ("author", r"Macr\`\i , Emanuele"),
        ("author", r"\AE and Smith, John"),
        ("author", r"Fran{\c{c}}ois, Jean"),
        ("author", r"\AE{} John"),
        ("author", r"{\AE} John"),
        ("publisher", r"\AE and Other Press"),
        ("publisher", r"{\AE} and Other Press"),
        ("title", r"\AE Test"),
    )
    sources: list[str] = []
    for index, (field, value) in enumerate(cases):
        source = f"@book{{after{index},{field}={{{value}}}}}"
        library = bibtexparser.parse_string(source)
        bibliography = Bibliography(library.blocks, IdentityIndex(library.entries))
        normalize_latex_accents(bibliography)
        normalized = bibliography.resolve(f"after{index}").fields_dict[field].value
        sources.extend(
            (
                f"@book{{before{index},{field}={{{value}}}}}",
                f"@book{{after{index},{field}={{{normalized}}}}}",
            )
        )
    (tmp_path / "input.bib").write_text("\n".join(sources) + "\n", encoding="utf-8")
    result = subprocess.run(
        [biber, "--tool", "--output-xname", "--output-file=processed.bib", "input.bib"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    parsed = bibtexparser.parse_string((tmp_path / "processed.bib").read_text(encoding="utf-8"))
    assert not parsed.failed_blocks
    values = {
        entry.key: {field.key.casefold(): str(field.value) for field in entry.fields}
        for entry in parsed.entries
    }
    for index, (field, _value) in enumerate(cases):
        before = values[f"before{index}"][field]
        after = values[f"after{index}"][field]
        if field == "author":
            # Encoding and retained brace layers may differ. Name-part boundaries
            # must not; exact converted characters are covered by the unit tests.
            parts = r"\b(family|given|prefix|suffix)="
            assert re.findall(parts, before) == re.findall(parts, after), (before, after)
        elif field == "publisher":
            # These fixtures have no literal 'and' inside publisher names.
            assert before.count(" and ") == after.count(" and "), (before, after)
        else:
            assert before == after

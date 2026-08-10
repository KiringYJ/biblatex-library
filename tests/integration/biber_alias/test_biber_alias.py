"""Executable regression gate for BibLaTeX/Biber citation-key aliases."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

FIXTURE_ROOT = Path(__file__).parent
EXPECTED_BIBER_VERSION = "2.21"
EXPECTED_BIBLATEX_VERSION = "3.21"
BAD_DIAGNOSTIC = re.compile(r"\b(?:WARN|ERROR)\b", re.I)


def _required_tool(name: str) -> str:
    executable = shutil.which(name)
    if executable is None:
        pytest.skip(f"integration tool is not installed: {name}")
        raise AssertionError("pytest.skip unexpectedly returned")
    return executable


def _run(command: list[str], working_directory: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=working_directory,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _prepare_document(temporary_path: Path, citation_keys: str) -> None:
    shutil.copyfile(FIXTURE_ROOT / "library.bib", temporary_path / "library.bib")
    template = (FIXTURE_ROOT / "document.tex").read_text(encoding="utf-8")
    (temporary_path / "document.tex").write_text(
        template.replace("CITATION_KEYS", citation_keys),
        encoding="utf-8",
    )


def _compile_biber_fixture(temporary_path: Path, citation_keys: str) -> tuple[str, str]:
    latex = _required_tool("pdflatex")
    biber = _required_tool("biber")
    _prepare_document(temporary_path, citation_keys)

    latex_result = _run(
        [latex, "-interaction=nonstopmode", "-halt-on-error", "document.tex"],
        temporary_path,
    )
    assert latex_result.returncode == 0, latex_result.stdout + latex_result.stderr

    biber_result = _run([biber, "document"], temporary_path)
    assert biber_result.returncode == 0, biber_result.stdout + biber_result.stderr
    return (
        (temporary_path / "document.bbl").read_text(encoding="utf-8"),
        (temporary_path / "document.blg").read_text(encoding="utf-8"),
    )


@pytest.mark.integration
@pytest.mark.parametrize("citation_keys", ["old-key", "new-key", "old-key,new-key", "CaseAlias"])
def test_supported_citations_emit_one_entry_without_alias_diagnostics(
    tmp_path: Path, citation_keys: str
) -> None:
    """Each supported canonical/alias citation selection emits one clean entry."""
    bbl, blg = _compile_biber_fixture(tmp_path, citation_keys)

    assert len(re.findall(r"\\entry\{new-key\}", bbl)) == 1
    assert BAD_DIAGNOSTIC.search(blg) is None


@pytest.mark.integration
def test_alias_lookup_is_ascii_case_sensitive(tmp_path: Path) -> None:
    """A lowercase spelling does not resolve a differently cased alias."""
    _, blg = _compile_biber_fixture(tmp_path, "casealias")

    assert re.search(r"WARN.*didn't find a database entry for 'casealias'", blg, re.I)


@pytest.mark.integration
def test_toolchain_versions_match_phase_zero_evidence() -> None:
    """The executable gate stays pinned to Biber and active BibLaTeX versions."""
    biber = _required_tool("biber")
    kpsewhich = _required_tool("kpsewhich")

    biber_result = _run([biber, "--version"], FIXTURE_ROOT)
    assert biber_result.returncode == 0
    version_pattern = rf"biber version:\s*{re.escape(EXPECTED_BIBER_VERSION)}\b"
    assert re.search(version_pattern, biber_result.stdout)

    biblatex_result = _run([kpsewhich, "biblatex.sty"], FIXTURE_ROOT)
    assert biblatex_result.returncode == 0
    biblatex_path = Path(biblatex_result.stdout.strip())
    biblatex_source = biblatex_path.read_text(encoding="utf-8", errors="replace")
    assert rf"\def\abx@version{{{EXPECTED_BIBLATEX_VERSION}}}" in biblatex_source

"""Source-preserving, finite-grammar LaTeX accent normalization regressions."""

import unicodedata

import bibtexparser
import pytest

from biblio.bibliography import Bibliography, IdentityIndex
from biblio.normalize.accents import _convert_value, normalize_latex_accents


@pytest.mark.parametrize(
    "before, after",
    [
        (r"Jos\'e", "José"),
        (r"Mart{\'i}", "Mart{í}"),
        (r"\c{c}", "{ç}"),
        (r"Fran{\c{c}}ois", "Fran{{ç}}ois"),
        (r"\textbf{\"O}", r"\textbf{Ö}"),
        (r"\textit{\'{E}}", r"\textit{{É}}"),
        (r"{\'{E}}", "{{É}}"),
        (r"\v S", "Š"),
        (r"\H{o}", "{ő}"),
        (r"\ae word", "æword"),
        (r"\ae{} word", "æ{} word"),
        (r"{\AE} and \oe{}", "{Æ} and œ{}"),
        (r"Macr\`\i", "Macrì"),
        (r"\'\j", "j́"),
        (r"\'{\i}", "{í}"),
        ("\\ae\t  word", "æword"),
        (r"\ae{}", "æ{}"),
        (r"\textbf {Jos\'e}", r"\textbf {José}"),
        (r"G\"odel and \ss", "Gödel and ß"),
        (r"Victor\ Mikhailovich", r"Victor\ Mikhailovich"),
    ],
)
def test_supported_complete_commands_preserve_group_topology(before: str, after: str) -> None:
    assert _convert_value(before) == after
    assert _convert_value(after) == after


@pytest.mark.parametrize(
    "value",
    [
        r"\LaTeX",
        r"\left",
        r"\langle",
        r"\iota",
        r"\ofoo",
        r"\aeon",
        r"Jos\'e and \unknown{\ae}",
        r"Jos\'e and \foo\ae",
        r"\textbf\ae",
        r"\textbf[option]{\ae}",
        r"\textbf",
        r"\textbf{}\foo",
        r"\string\ae",
        r"\url{https://example.test/\ae}",
        r"\href{x}{\ae}",
        r"\verb|\ae|",
        r"\verb*+\ae+",
        r"\begin{verbatim}\ae\end{verbatim}",
        r"\def\foo{\ae}",
        r"\newcommand{\foo}{\ae}",
        r"\let\foo\ae",
        r"\catcode`\%=12 \ae",
        r"Jos\'e $\ae$",
        r"Jos\'e $$x$$",
        r"Jos\'e \(x\)",
        r"Jos\'e \[x\]",
        "Jos\\'e % \\ae\nword",
        r"Jos\'e #1",
        r"\'",
        r"\c",
        r"\'{ab}",
        r"\'{}",
        r"\'{ e }",
        r"\'{{e}}",
        r"\`\iota",
        r"\'\jmath",
        r"\'\i@custom",
        r"Jos\'e {unclosed",
        r"Jos\'e }",
        "Jos\\'e \\",
        r"\unknown{\'e}",
        r"{\bf Jos\'e}",
        r"Jos\'e \ae@custom",
        r"\LaTeX\ae",
        r"\TeX\'e",
        r"\LaTeX\ae{} word",
    ],
)
def test_opaque_or_unsupported_context_preserves_whole_field(value: str) -> None:
    assert _convert_value(value) == value


@pytest.mark.parametrize(
    "name",
    [
        "doi",
        "isbn",
        "isbn13",
        "eprint",
        "url",
        "mrnumber",
        "zbl",
        "zbmath",
        "jfm",
        "oclc",
        "hdl",
        "acmdl_doi",
        "ids",
        "eprinttype",
        "archiveprefix",
        "eprintclass",
        "primaryclass",
        "file",
        "pdf",
        "localfile",
        "customfield",
        "crossref",
        "xdata",
    ],
)
def test_opaque_identifier_path_and_custom_fields_remain_exact(name: str) -> None:
    library = bibtexparser.parse_string(f"@book{{one,{name}={{Jos\\'e}},title={{Jos\\'e}}}}")
    bibliography = Bibliography(library.blocks, IdentityIndex(library.entries))
    report = normalize_latex_accents(bibliography)
    assert bibliography.resolve("one").fields_dict[name].value == r"Jos\'e"
    assert bibliography.resolve("one").fields_dict["title"].value == "José"
    assert report.converted == {"one": ("title",)}


def test_text_fields_case_insensitivity_and_exact_reports() -> None:
    library = bibtexparser.parse_string(
        r"@book{one,AUTHOR={Jos\'e Mart{\'i}},TITLE={\textbf{\"O}},"
        r"publisher={G\ae{}teborg Press},mrreviewer={Victor\ Mikhailovich}}"
    )
    bibliography = Bibliography(library.blocks, IdentityIndex(library.entries))
    report = normalize_latex_accents(bibliography)
    assert report.converted == {"one": ("AUTHOR", "TITLE", "publisher")}
    assert report.total_fields == 3
    assert report.changes.changed_keys == ("one",)
    assert bibliography.resolve("one").fields_dict["mrreviewer"].value == r"Victor\ Mikhailovich"
    assert report.changes.field_deltas[0].before == r"Jos\'e Mart{\'i}"
    assert report.changes.field_deltas[0].after == "José Mart{í}"
    assert not normalize_latex_accents(bibliography).changes.changed


def test_deeply_nested_groups_do_not_recurse() -> None:
    value = "{" * 2000 + r"Jos\'e" + "}" * 2000
    assert _convert_value(value) == "{" * 2000 + "José" + "}" * 2000


@pytest.mark.parametrize(
    "before, after",
    [
        (r"\LaTeX and \textbf{\"O} and \textit{É}", r"\LaTeX and \textbf{Ö} and \textit{É}"),
        (r"\LaTeX \ae", r"\LaTeX æ"),
        (r"\ae\oe", "æœ"),
        (r"\ae\'{e}", "æ{é}"),
        (r"\{Jos\'e\}", r"\{José\}"),
        (r"\'e and \%", r"é and \%"),
        (r"Macr\`\i , Emanuele", "Macrì, Emanuele"),
    ],
)
def test_known_token_boundaries_remain_valid(before: str, after: str) -> None:
    assert _convert_value(before) == after
    assert _convert_value(after) == after


@pytest.mark.parametrize("value", ["\\ae\nword", "\\ae\n\nword", "\\'\ne", r"\aeé"])
def test_unsupported_controlword_delimiters_remain_opaque(value: str) -> None:
    assert _convert_value(value) == value


@pytest.mark.parametrize("control", ["\x00", "\x0b", "\x0c", "\x7f"])
def test_raw_control_characters_make_the_field_opaque(control: str) -> None:
    value = r"Jos\'e" + control
    assert _convert_value(value) == value


@pytest.mark.parametrize("letter, dotless", [("i", "ı"), ("j", "ȷ")])
@pytest.mark.parametrize(
    "accent, mark, retains_dotless",
    [
        ("'", "\u0301", False),
        ("`", "\u0300", False),
        ('"', "\u0308", False),
        ("^", "\u0302", False),
        ("~", "\u0303", False),
        ("=", "\u0304", False),
        (".", "\u0307", True),
        ("d", "\u0323", True),
        ("b", "\u0331", True),
        ("H", "\u030b", False),
        ("c", "\u0327", True),
        ("k", "\u0328", True),
        ("r", "\u030a", False),
        ("u", "\u0306", False),
        ("v", "\u030c", False),
    ],
)
def test_dotless_operands_across_every_supported_accent(
    accent: str, mark: str, retains_dotless: bool, letter: str, dotless: str
) -> None:
    # Unicode 17 sections 3.6/P9 and 7.1 distinguish below marks and explicit
    # dotless bases from the conventional soft-dotted base for above accents.
    expected = unicodedata.normalize("NFC", (dotless if retains_dotless else letter) + mark)
    for source, result in [
        (f"\\{accent}{{\\{letter}}}", "{" + expected + "}"),
        (f"\\{accent}\\{letter}", expected),
        (f"{{\\{accent}\\{letter}}}", "{" + expected + "}"),
    ]:
        assert _convert_value(source) == result
        assert _convert_value(result) == result
    # Explicit Unicode bases are not inferred or replaced, even above accents.
    assert _convert_value(f"\\{accent}{{{dotless}}}") == (
        "{" + unicodedata.normalize("NFC", dotless + mark) + "}"
    )
    assert _convert_value(f"\\{accent}{{{letter}}}") == (
        "{" + unicodedata.normalize("NFC", letter + mark) + "}"
    )


def test_dot_above_keeps_the_explicit_dotless_base_and_one_combining_dot() -> None:
    assert _convert_value(r"\.{\i}") == "{\u0131\u0307}"
    assert _convert_value(r"\.{\j}") == "{\u0237\u0307}"
    assert _convert_value(r"\.{\i}") != "{i\u0307}"
    assert _convert_value(r"\.{\j}") != "{j\u0307}"


def test_below_dot_does_not_add_the_dotted_base() -> None:
    assert _convert_value(r"\d{\i}") == _convert_value(r"\d{ı}") == "{\u0131\u0323}"
    assert _convert_value(r"\d{\j}") == _convert_value(r"\d{ȷ}") == "{\u0237\u0323}"
    assert _convert_value(r"\d{i}") == "{ị}"

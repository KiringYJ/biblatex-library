"""Convert a finite set of text accents without regenerating LaTeX source."""

import unicodedata
from dataclasses import dataclass, field

from biblio.bibliography import Bibliography
from biblio.results import ChangeSet, FieldDelta

from .names import NAME_FIELDS
from .tex import TextToken, scan_text

_ACCENT_COMBINING = {
    "'": "\u0301",
    "`": "\u0300",
    '"': "\u0308",
    "^": "\u0302",
    "~": "\u0303",
    "=": "\u0304",
    ".": "\u0307",
    "d": "\u0323",
    "b": "\u0331",
    "H": "\u030b",
    "c": "\u0327",
    "k": "\u0328",
    "r": "\u030a",
    "u": "\u0306",
    "v": "\u030c",
}
_SPECIAL_LETTERS = {
    "ae": "æ",
    "AE": "Æ",
    "oe": "œ",
    "OE": "Œ",
    "aa": "å",
    "AA": "Å",
    "ss": "ß",
    "o": "ø",
    "O": "Ø",
    "l": "ł",
    "L": "Ł",
    "i": "ı",
    "j": "ȷ",
}
# Below marks retain a dotless operand; an explicit dot-above must not also
# introduce a dotted base. See Unicode 17, sections 3.6 (P9) and 7.1.
_DOTLESS_BASE_ACCENTS = frozenset({"d", "b", "c", "k", "."})
_TEXT_WRAPPERS = frozenset(
    {
        "textbf",
        "textit",
        "texttt",
        "textrm",
        "textsf",
        "textsc",
        "textsl",
        "textnormal",
        "emph",
        "mbox",
    }
)
_LITERAL_COMMANDS = frozenset({"{", "}", "%", "&", "#", "_", " ", "LaTeX", "TeX"})
_TEXT_FIELDS = NAME_FIELDS | frozenset(
    {
        "title",
        "subtitle",
        "titleaddon",
        "shorttitle",
        "booktitle",
        "booksubtitle",
        "booktitleaddon",
        "maintitle",
        "mainsubtitle",
        "maintitleaddon",
        "journaltitle",
        "journalsubtitle",
        "journal",
        "fjournal",
        "shortjournal",
        "issuetitle",
        "issuesubtitle",
        "series",
        "eventtitle",
        "eventtitleaddon",
        "publisher",
        "institution",
        "organization",
        "location",
        "origpublisher",
        "origlocation",
        "origtitle",
        "note",
        "annote",
        "annotation",
        "abstract",
        "keywords",
        "howpublished",
        "addendum",
        "venue",
        "mrreviewer",
    }
)


@dataclass(frozen=True, slots=True)
class AccentNormalizationReport:
    """Summary of exact source-span replacements in supported text fields."""

    converted: dict[str, tuple[str, ...]]
    changes: ChangeSet = field(default_factory=ChangeSet)

    @property
    def total_fields(self) -> int:
        return sum(len(fields) for fields in self.converted.values())


def normalize_latex_accents(bibliography: Bibliography) -> AccentNormalizationReport:
    """Normalize supported text only; identifiers, paths, and custom fields are opaque."""
    converted: dict[str, tuple[str, ...]] = {}
    deltas: list[FieldDelta] = []
    for entry in bibliography:
        changed_fields: list[str] = []
        for entry_field in entry.fields:
            if entry_field.key.casefold() not in _TEXT_FIELDS:
                continue
            before = str(entry_field.value)
            after = _convert_value(before)
            if after == before:
                continue
            entry_field.value = after
            changed_fields.append(entry_field.key)
            deltas.append(FieldDelta(entry.key, entry_field.key, before, after))
        if changed_fields:
            converted[entry.key] = tuple(changed_fields)
    return AccentNormalizationReport(converted, ChangeSet(tuple(converted), tuple(deltas)))


def _convert_value(value: str) -> str:
    """Replace complete supported commands while keeping all existing groups.

    Even accent-operand braces remain: ``\\c{c}`` becomes ``{ç}``. An unknown
    command or unsupported argument grammar preserves the complete field.
    """
    if "\\" not in value:
        return value
    tokens = scan_text(value)
    if tokens is None:
        return value
    replacements: list[tuple[int, int, str]] = []
    retained_commands: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.kind != "command":
            index += 1
            continue
        if token.value in _ACCENT_COMBINING:
            argument = _accent_argument(tokens, index + 1, token.value)
            if argument is None:
                return value
            next_index, base, grouped = argument
            composed = unicodedata.normalize("NFC", base + _ACCENT_COMBINING[token.value])
            replacement = "{" + composed + "}" if grouped else composed
            replacements.append((token.start, tokens[next_index - 1].end, replacement))
            index = next_index
            continue
        if token.value in _SPECIAL_LETTERS:
            replacements.append((token.start, token.end, _SPECIAL_LETTERS[token.value]))
        elif token.value in _TEXT_WRAPPERS:
            if index + 1 == len(tokens) or tokens[index + 1].kind != "open":
                return value
            retained_commands.append(token.value)
        elif token.value not in _LITERAL_COMMANDS:
            return value
        else:
            retained_commands.append(token.value)
        index += 1

    pieces: list[str] = []
    previous = 0
    for start, end, replacement in replacements:
        pieces.extend((value[previous:start], replacement))
        previous = end
    pieces.append(value[previous:])
    normalized = "".join(pieces)
    # A removed command boundary must not extend a retained control word.
    output_tokens = scan_text(normalized)
    if (
        output_tokens is None
        or [token.value for token in output_tokens if token.kind == "command"] != retained_commands
    ):
        return value
    return normalized


def _accent_argument(
    tokens: tuple[TextToken, ...], index: int, accent: str
) -> tuple[int, str, bool] | None:
    while index < len(tokens) and tokens[index].kind == "space":
        if tokens[index].value not in " \t":
            return None
        index += 1
    if index == len(tokens):
        return None
    grouped = tokens[index].kind == "open"
    if grouped:
        index += 1
    if index == len(tokens):
        return None
    token = tokens[index]
    if token.kind == "character" and token.value.isalpha():
        base = token.value
    elif token.kind == "command" and token.value in {"i", "j"}:
        base = _SPECIAL_LETTERS[token.value] if accent in _DOTLESS_BASE_ACCENTS else token.value
    else:
        return None
    index += 1
    if grouped:
        if index == len(tokens) or tokens[index].kind != "close":
            return None
        index += 1
    return index, base, grouped

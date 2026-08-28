"""A bounded source lexer, not a TeX evaluator.

The supported surface is balanced text groups, control sequences, and ordinary
text. Math, comments, parameter syntax, and active characters make the complete
field opaque. Callers must separately allowlist commands and their arguments.
"""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class TextToken:
    kind: Literal["character", "space", "open", "close", "command"]
    value: str
    start: int
    end: int
    depth: int


def scan_text(value: str) -> tuple[TextToken, ...] | None:
    """Return source spans, or ``None`` for unsupported/unbalanced syntax.

    Control words include their swallowed horizontal delimiter whitespace.
    Newline delimiters are left opaque rather than evaluating TeX line states.
    Group validation is iterative, including for deeply nested input.
    """
    tokens: list[TextToken] = []
    depth = 0
    position = 0
    while position < len(value):
        start = position
        character = value[position]
        if (ord(character) < 32 and character not in "\t\r\n") or 127 <= ord(character) <= 159:
            return None
        if character in "$%#&_^~":
            return None
        if character == "\\":
            position += 1
            if position == len(value):
                return None
            command_start = position
            if value[position].isalpha() or value[position] == "@":
                while position < len(value) and (
                    value[position].isalpha() or value[position] == "@"
                ):
                    position += 1
                command = value[command_start:position]
                while position < len(value) and value[position] in " \t":
                    position += 1
                if position < len(value) and value[position] in "\r\n":
                    return None
            else:
                command = value[position]
                position += 1
            tokens.append(TextToken("command", command, start, position, depth))
            continue
        position += 1
        if character == "{":
            tokens.append(TextToken("open", character, start, position, depth))
            depth += 1
        elif character == "}":
            if depth == 0:
                return None
            depth -= 1
            tokens.append(TextToken("close", character, start, position, depth))
        elif character.isspace():
            tokens.append(TextToken("space", character, start, position, depth))
        else:
            tokens.append(TextToken("character", character, start, position, depth))
    return tuple(tokens) if depth == 0 else None

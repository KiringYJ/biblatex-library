"""Pure citekey name and year extraction primitives."""

import re
import unicodedata


def extract_lastname(author: str, sortname: str = "") -> str:
    """Return a normalized first-author surname for a generated citekey."""
    if not author:
        return "unknown"

    first_author = author.split(" and ", 1)[0].strip()
    if first_author.startswith("{") and first_author.endswith("}"):
        organization = first_author.strip("{}")
        source = sortname.split() if sortname else organization.split()
        lastname = source[0] if source else "unknown"
    elif "," in first_author:
        lastname = first_author.split(",", 1)[0].strip()
    else:
        parts = first_author.split()
        lastname = parts[-1] if parts else "unknown"

    decomposed = unicodedata.normalize("NFD", lastname)
    without_accents = "".join(
        character for character in decomposed if unicodedata.category(character) != "Mn"
    )
    return re.sub(r"[^a-zA-Z]", "", without_accents).lower() or "unknown"


def extract_year(date: str) -> str:
    """Return the first date/range component, or ``unknown`` when empty."""
    if not date:
        return "unknown"
    return date.split("/", 1)[0].split("-", 1)[0].strip() or "unknown"


def citekey_stem(
    *,
    shorthand: str | None = None,
    author: str | None = None,
    editor: str | None = None,
    sortname: str | None = None,
    date: str | None = None,
    year: str | None = None,
) -> tuple[str, str]:
    """Return the shared name/year stem used by add and promotion."""
    shorthand_value = (shorthand or "").strip()
    if shorthand_value:
        decomposed = unicodedata.normalize("NFD", shorthand_value)
        without_accents = "".join(
            character for character in decomposed if unicodedata.category(character) != "Mn"
        )
        name = re.sub(r"[^a-zA-Z]", "", without_accents).lower() or "unknown"
    else:
        creator = author if author is not None else (editor or "")
        name = extract_lastname(creator, sortname or "")

    date_value = date if date is not None else (year or "")
    return name, extract_year(date_value)

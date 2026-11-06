"""Structured pagination under the explicitly marked MR article convention."""

import re
from dataclasses import dataclass, field

from bibtexparser.model import Entry, Field

from biblio.bibliography import Bibliography
from biblio.results import ChangeSet, FieldDelta

from .mr import MR_FIELDS, has_mr_metadata

_IDENTIFIER = r"[A-Za-z]*[0-9]+(?:\.[0-9]+)*"
_LABEL = r"(?:Paper(?:\s+No\.)?|Art\.(?:\s+ID)?)"
_FLAGS = re.IGNORECASE | re.ASCII
_PAGINATION = re.compile(
    rf"{_LABEL}\s+(?P<eid>{_IDENTIFIER})(?:\s*,\s*(?P<total>[1-9][0-9]*)(?:\s+pp\.)?)?",
    _FLAGS,
)
_LABEL_ATTEMPT = re.compile(rf"{_LABEL}(?=\s|$)", _FLAGS)
_BARE_PAIR = re.compile(
    rf"{_IDENTIFIER}\s*,\s*(?:[1-9][0-9]*(?:\s+pp\.)?|"
    r"[ivxlcdm]+\s*[+,]\s*[1-9][0-9]*|front\s+matter\s*\+\s*[1-9][0-9]*)",
    _FLAGS,
)
_PARTICIPATING_FIELDS = MR_FIELDS | {
    "pages",
    "eid",
    "pagetotal",
    "chapter",
    "pagination",
    "bookpagination",
}


@dataclass(frozen=True, slots=True)
class ArticlePagination:
    """Exact article identifier and optional positive page count."""

    eid: str
    pagetotal: str | None = None


@dataclass(frozen=True, slots=True)
class ArticlePaginationReport:
    """Article pagination changes, conflicting targets, and review-only inputs."""

    conflicts: tuple[str, ...] = ()
    ambiguous: tuple[str, ...] = ()
    changes: ChangeSet = field(default_factory=ChangeSet)


def parse_article_pagination(value: str) -> ArticlePagination | None:
    """Parse only labeled identifiers with an optional explicit Arabic count."""
    match = _PAGINATION.fullmatch(value.strip())
    if match is None:
        return None
    return ArticlePagination(match["eid"], match["total"])


def is_article_pagination_candidate(value: str) -> bool:
    """Recognize bounded labeled attempts and ambiguous identifier/extent pairs."""
    stripped = value.strip()
    return _LABEL_ATTEMPT.match(stripped) is not None or _BARE_PAIR.fullmatch(stripped) is not None


def is_mr_article_pagination(entry: Entry) -> bool:
    """Check the marked article source and scope, without comparing targets."""
    fields = {item.key.casefold(): str(item.value) for item in entry.fields}
    return (
        entry.entry_type.casefold() == "article"
        and len(fields) == len(entry.fields)
        and has_mr_metadata(entry)
        and "pages" in fields
        and "chapter" not in fields
        and all(fields.get(unit, "page") == "page" for unit in ("pagination", "bookpagination"))
        and parse_article_pagination(fields["pages"]) is not None
    )


def normalize_article_pagination(bibliography: Bibliography) -> ArticlePaginationReport:
    """Atomically replace supported marked article pages with structured fields."""
    entries = [(entry, _participating_fields(entry)) for entry in bibliography]
    changed: list[str] = []
    conflicts: list[str] = []
    ambiguous: list[str] = []
    deltas: list[FieldDelta] = []
    for entry, fields in entries:
        if entry.entry_type.casefold() != "article" or "pages" not in fields:
            continue
        source = fields["pages"]
        value = str(source.value)
        if not is_article_pagination_candidate(value):
            continue
        parsed = parse_article_pagination(value)
        if parsed is None or not is_mr_article_pagination(entry):
            ambiguous.append(entry.key)
            continue
        targets = [("eid", parsed.eid)]
        if parsed.pagetotal is not None:
            targets.append(("pagetotal", parsed.pagetotal))
        if any(name in fields and str(fields[name].value) != target for name, target in targets):
            conflicts.append(entry.key)
            continue
        replacement = [Field(name, target) for name, target in targets if name not in fields]
        position = entry.fields.index(source)
        entry.fields[position : position + 1] = replacement
        deltas.append(FieldDelta(entry.key, "pages", value, None))
        deltas.extend(
            FieldDelta(entry.key, item.key, None, str(item.value)) for item in replacement
        )
        changed.append(entry.key)
    return ArticlePaginationReport(
        tuple(conflicts), tuple(ambiguous), ChangeSet(tuple(changed), tuple(deltas))
    )


def _participating_fields(entry: Entry) -> dict[str, Field]:
    fields: dict[str, Field] = {}
    for entry_field in entry.fields:
        name = entry_field.key.casefold()
        if name not in _PARTICIPATING_FIELDS:
            continue
        if name in fields:
            raise ValueError(f"entry '{entry.key}' has duplicate '{name}' fields")
        fields[name] = entry_field
    return fields

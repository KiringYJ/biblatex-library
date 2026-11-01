"""Bounded Hexagon export conversion without contributor-role inference."""

from dataclasses import dataclass, field

from bibtexparser.model import Entry, Field

from biblio.bibliography import Bibliography
from biblio.identifiers import canonicalize_hexagon_identifier, hexagon_comparison_token
from biblio.results import ChangeSet, FieldDelta

_EXPORT_PREFIX = "Hexagon preprint hexagon:"
_URL_PREFIX = "https://hexagonmath.org/"


@dataclass(frozen=True, slots=True)
class HexagonNormalizationReport:
    """Changes and preserved metadata requiring bibliographic review."""

    changes: ChangeSet = field(default_factory=ChangeSet)
    conflicts: tuple[tuple[str, str], ...] = ()


def normalize_hexagon_fields(bibliography: Bibliography) -> HexagonNormalizationReport:
    """Convert explicit Hexagon exports/eprints to version-free work identifiers.

    Only the documented miscellaneous/online export wrapper supplies a missing
    eprint. Other entry types and contributor roles are preserved. A URL or
    temporary citekey alone never establishes Hexagon identity.
    """
    entries = [(entry, _fields(entry)) for entry in bibliography]
    deltas: list[FieldDelta] = []
    changed: list[str] = []
    conflicts: list[tuple[str, str]] = []
    for entry, fields in entries:
        try:
            values = _normalization_values(entry, fields)
        except ValueError as error:
            conflicts.append((entry.key, str(error)))
            continue
        if values is None:
            continue
        eprint, imported = values
        entry_deltas: list[FieldDelta] = []
        updates = {"eprint": eprint, "eprinttype": "hexagon"}
        for name, value in updates.items():
            existing = fields.get(name)
            before = str(existing.value) if existing is not None else None
            if before == value:
                continue
            if existing is None:
                entry.fields.append(Field(name, value))
            else:
                existing.value = value
            entry_deltas.append(FieldDelta(entry.key, name, before, value))
        for name in ("archiveprefix", *(("key", "howpublished") if imported else ())):
            existing = fields.get(name)
            if existing is not None:
                entry.fields.remove(existing)
                entry_deltas.append(FieldDelta(entry.key, name, str(existing.value), None))
        url = fields.get("url")
        if url is not None and matches_hexagon_url(str(url.value), eprint):
            entry.fields.remove(url)
            entry_deltas.append(FieldDelta(entry.key, "url", str(url.value), None))
        if entry.entry_type.casefold() == "misc":
            before = entry.entry_type
            entry.entry_type = "online"
            entry_deltas.append(FieldDelta(entry.key, "entry_type", before, "online"))
        if entry_deltas:
            changed.append(entry.key)
            deltas.extend(entry_deltas)
    return HexagonNormalizationReport(ChangeSet(tuple(changed), tuple(deltas)), tuple(conflicts))


def matches_hexagon_url(url: str, identifier: str) -> bool:
    """Match an exact Hexagon landing URL for the same version-free work."""
    if not url.startswith(_URL_PREFIX):
        return False
    raw = url[len(_URL_PREFIX) :]
    try:
        return raw == hexagon_comparison_token(raw) and canonicalize_hexagon_identifier(
            raw
        ) == canonicalize_hexagon_identifier(identifier)
    except ValueError:
        return False


def explicit_hexagon_eprint(entry: Entry) -> str | None:
    """Return an explicit valid Hexagon eprint only when its aliases agree."""
    fields = _fields(entry)
    types = [
        str(fields[name].value).strip().casefold()
        for name in ("eprinttype", "archiveprefix")
        if name in fields
    ]
    eprint = fields.get("eprint")
    if not types or any(value != "hexagon" for value in types) or eprint is None:
        return None
    value = str(eprint.value)
    try:
        hexagon_comparison_token(value)
    except ValueError:
        return None
    return value


def _fields(entry: Entry) -> dict[str, Field]:
    fields: dict[str, Field] = {}
    for item in entry.fields:
        name = item.key.casefold()
        if name in fields:
            raise ValueError(f"entry '{entry.key}' has duplicate '{name}' fields")
        fields[name] = item
    return fields


def _normalization_values(entry: Entry, fields: dict[str, Field]) -> tuple[str, bool] | None:
    types = [
        str(fields[name].value).strip().casefold()
        for name in ("eprinttype", "archiveprefix")
        if name in fields
    ]
    howpublished = str(fields["howpublished"].value) if "howpublished" in fields else ""
    imported = howpublished.startswith("Hexagon preprint ")
    explicit = "hexagon" in types
    if not explicit and (not imported or entry.entry_type.casefold() not in {"misc", "online"}):
        return None
    if any(value != "hexagon" for value in types):
        raise ValueError("eprinttype:conflict")
    if "eprintclass" in fields or "primaryclass" in fields:
        raise ValueError("eprintclass:unsupported")
    exported: str | None = None
    if imported:
        if not howpublished.startswith(_EXPORT_PREFIX):
            raise ValueError("howpublished:unsupported")
        exported = howpublished[len(_EXPORT_PREFIX) :]
        if hexagon_comparison_token(exported) != exported:
            raise ValueError("howpublished:unsupported")
    if "eprint" in fields:
        eprint = str(fields["eprint"].value)
    elif exported is not None:
        eprint = exported
    else:
        raise ValueError("eprint:missing")
    token = canonicalize_hexagon_identifier(eprint)
    if exported is not None and token != canonicalize_hexagon_identifier(exported):
        raise ValueError("eprint:conflict")
    if imported:
        if "key" in fields and canonicalize_hexagon_identifier(str(fields["key"].value)) != token:
            raise ValueError("key:conflict")
        if "url" in fields and not matches_hexagon_url(str(fields["url"].value), token):
            raise ValueError("url:conflict")
    return token, imported

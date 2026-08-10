"""Exact identifier inventory models, codecs, and BibLaTeX projections."""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from bibtexparser.model import Entry, Field

from .identifiers import isbn_comparison_token, legacy_doi_comparison_token

SUPPORTED_IDENTIFIER_KINDS = (
    "doi",
    "isbn13",
    "arxiv",
    "url",
    "mrnumber",
    "zbl",
    "zbmath",
    "jfm",
    "oclc",
    "hdl",
    "acmdl_doi",
)
SUPPORTED_IDENTIFIER_KIND_SET = frozenset(SUPPORTED_IDENTIFIER_KINDS)


@dataclass(frozen=True, slots=True)
class KeyHistory:
    """Exact identifier input that produced one canonical or alias key."""

    key: str
    main_identifier: str
    identifier: str


@dataclass(slots=True)
class IdentifierRecord:
    """Complete exact identifier inventory and optional key provenance."""

    main_identifier: str
    identifiers: dict[str, str]
    identifier_alternates: dict[str, tuple[str, ...]] = field(default_factory=dict)
    key_history: tuple[KeyHistory, ...] = ()

    def inventory_values(self, kind: str) -> tuple[str, ...]:
        """Return the primary value followed by exact same-kind alternates."""
        primary = self.identifiers.get(kind)
        alternates = self.identifier_alternates.get(kind, ())
        return (*((primary,) if primary is not None else ()), *alternates)


type IdentifierCollection = dict[str, IdentifierRecord]


def _object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key '{key}'")
        result[key] = value
    return result


def _decode_json(data: bytes, description: str) -> object:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"{description} is not valid UTF-8") from error
    try:
        return json.loads(text, object_pairs_hook=_object_pairs)
    except json.JSONDecodeError as error:
        raise ValueError(f"{description} is not valid JSON: {error.msg}") from error


def _object(value: object, description: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{description} must be an object")
    result: dict[str, object] = {}
    for raw_key, raw_value in value.items():
        if not isinstance(raw_key, str):
            raise ValueError(f"{description} keys must be strings")
        result[raw_key] = raw_value
    return result


def _string_map(value: object, description: str) -> dict[str, str]:
    raw_map = _object(value, description)
    result: dict[str, str] = {}
    for raw_kind, raw_identifier in raw_map.items():
        if not isinstance(raw_identifier, str):
            raise ValueError(f"{description} must map string kinds to string values")
        result[raw_kind] = raw_identifier
    return result


def _alternates_map(value: object, description: str) -> dict[str, tuple[str, ...]]:
    raw_map = _object(value, description)
    result: dict[str, tuple[str, ...]] = {}
    for raw_kind, raw_values in raw_map.items():
        if not isinstance(raw_values, list):
            raise ValueError(f"{description} must map string kinds to arrays")
        values: list[str] = []
        for raw_identifier in raw_values:
            if not isinstance(raw_identifier, str):
                raise ValueError(f"{description} values must be strings")
            values.append(raw_identifier)
        result[raw_kind] = tuple(values)
    return result


def _key_history(value: object, description: str) -> tuple[KeyHistory, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{description} must be an array")
    result: list[KeyHistory] = []
    expected = {"key", "main_identifier", "identifier"}
    for index, raw_item in enumerate(value):
        item = _object(raw_item, f"{description}[{index}]")
        if set(item) != expected:
            raise ValueError(f"{description}[{index}] must contain exactly {sorted(expected)}")
        key = item["key"]
        main_identifier = item["main_identifier"]
        identifier = item["identifier"]
        if (
            not isinstance(key, str)
            or not isinstance(main_identifier, str)
            or not isinstance(identifier, str)
        ):
            raise ValueError(f"{description}[{index}] values must be strings")
        result.append(KeyHistory(key, main_identifier, identifier))
    return tuple(result)


def parse_identifier_collection(data: bytes) -> IdentifierCollection:
    """Parse the backward-compatible flat identifier collection."""
    raw_collection = _object(_decode_json(data, "identifier collection"), "identifier collection")

    collection: IdentifierCollection = {}
    allowed = {"main_identifier", "identifiers", "identifier_alternates", "key_history"}
    for raw_key, raw_record in raw_collection.items():
        record = _object(raw_record, f"identifier record '{raw_key}'")
        extra = set(record) - allowed
        if extra:
            raise ValueError(
                f"identifier record '{raw_key}' has unknown properties: {sorted(extra)}"
            )
        if "main_identifier" not in record or "identifiers" not in record:
            raise ValueError(
                f"identifier record '{raw_key}' requires main_identifier and identifiers"
            )
        main_identifier = record["main_identifier"]
        if not isinstance(main_identifier, str):
            raise ValueError(f"identifier record '{raw_key}' main_identifier must be a string")
        identifiers = _string_map(
            record["identifiers"], f"identifier record '{raw_key}' identifiers"
        )
        alternates = _alternates_map(
            record.get("identifier_alternates", {}),
            f"identifier record '{raw_key}' identifier_alternates",
        )
        history = _key_history(
            record.get("key_history", []), f"identifier record '{raw_key}' key_history"
        )
        collection[raw_key] = IdentifierRecord(main_identifier, identifiers, alternates, history)
    return collection


def serialize_identifier_collection(collection: Mapping[str, IdentifierRecord]) -> bytes:
    """Serialize an identifier collection deterministically as UTF-8 JSON."""
    encoded: dict[str, object] = {}
    for key, record in collection.items():
        raw_record: dict[str, object] = {
            "main_identifier": record.main_identifier,
            "identifiers": dict(record.identifiers),
        }
        if record.identifier_alternates:
            raw_record["identifier_alternates"] = {
                kind: list(values) for kind, values in record.identifier_alternates.items()
            }
        if record.key_history:
            raw_record["key_history"] = [
                {
                    "key": item.key,
                    "main_identifier": item.main_identifier,
                    "identifier": item.identifier,
                }
                for item in record.key_history
            ]
        encoded[key] = raw_record
    return (json.dumps(encoded, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def parse_add_order(data: bytes) -> tuple[str, ...]:
    """Parse a unique chronological key ledger."""
    raw_order = _decode_json(data, "add-order ledger")
    if not isinstance(raw_order, list):
        raise ValueError("add-order ledger must be an array")
    order: list[str] = []
    seen: set[str] = set()
    for raw_key in raw_order:
        if not isinstance(raw_key, str):
            raise ValueError("add-order ledger values must be strings")
        if raw_key in seen:
            raise ValueError(f"duplicate add-order key '{raw_key}'")
        seen.add(raw_key)
        order.append(raw_key)
    return tuple(order)


def serialize_add_order(order: Sequence[str]) -> bytes:
    """Serialize the chronological ledger deterministically as UTF-8 JSON."""
    keys = tuple(order)
    if any(not isinstance(key, str) for key in keys):
        raise ValueError("add-order ledger values must be strings")
    if len(set(keys)) != len(keys):
        raise ValueError("add-order ledger keys must be unique")
    return (json.dumps(keys, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def identifier_equality_token(kind: str, value: str) -> str:
    """Return a comparison-only token without changing the exact inventory value."""
    if kind in {"doi", "acmdl_doi"}:
        return legacy_doi_comparison_token(value)
    token = value.strip()
    if kind == "isbn13":
        return isbn_comparison_token(value)
    if kind == "arxiv":
        if token[:6].casefold() == "arxiv:":
            token = token[6:].strip()
        return token.casefold()
    if kind == "mrnumber":
        return token[2:] if token[:2].casefold() == "mr" else token
    if kind in {"zbl", "jfm", "oclc"}:
        return token.casefold()
    return token


def _fields(entry: Entry, name: str) -> tuple[Field, ...]:
    return tuple(field for field in entry.fields if field.key.casefold() == name)


def _single_field(entry: Entry, name: str) -> str | None:
    fields = _fields(entry, name)
    if len(fields) > 1:
        raise ValueError(f"entry '{entry.key}' has repeated '{name}' fields")
    return str(fields[0].value) if fields else None


def _acm_url_identifier(url: str | None) -> str | None:
    if url is None:
        return None
    parsed = urlsplit(url.strip())
    if parsed.scheme.casefold() not in {"http", "https"}:
        return None
    if parsed.netloc.casefold() != "dl.acm.org" or not parsed.path.casefold().startswith("/doi/"):
        return None
    candidate = parsed.path[len("/doi/") :]
    return candidate or None


def identifiers_from_entry(entry: Entry) -> dict[str, str]:
    """Project all eleven supported identifier kinds from one BibLaTeX entry."""
    result: dict[str, str] = {}
    for kind in SUPPORTED_IDENTIFIER_KINDS:
        if kind == "isbn13":
            value = _single_field(entry, "isbn")
        elif kind == "arxiv":
            eprint = _single_field(entry, "eprint")
            eprinttype = _single_field(entry, "eprinttype")
            archiveprefix = _single_field(entry, "archiveprefix")
            marker = eprinttype if eprinttype is not None else archiveprefix
            value = eprint if marker is not None and marker.strip().casefold() == "arxiv" else None
        elif kind == "acmdl_doi":
            direct = _single_field(entry, "acmdl_doi")
            from_url = _acm_url_identifier(_single_field(entry, "url"))
            if (
                direct is not None
                and from_url is not None
                and identifier_equality_token(kind, direct)
                != identifier_equality_token(kind, from_url)
            ):
                raise ValueError(f"entry '{entry.key}' has disagreeing acmdl_doi field and ACM URL")
            value = direct if direct is not None else from_url
        else:
            value = _single_field(entry, kind)
        if value is not None and value != "":
            result[kind] = value
    return result

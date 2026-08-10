"""Read-only evidence collector for a legacy three-file consumer workspace."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict, cast

import bibtexparser


class LegacyIdentifierRecord(TypedDict):
    """One record in the retired identifier collection."""

    main_identifier: str
    identifiers: dict[str, str]


@dataclass(frozen=True)
class ConsumerAudit:
    """Immutable evidence gathered without writing to any input path."""

    bibliography_sha256: str
    identifiers_sha256: str
    add_order_sha256: str
    bibliography_keys: tuple[str, ...]
    identifier_keys: tuple[str, ...]
    add_order_keys: tuple[str, ...]
    identifier_kinds: frozenset[str]
    historical_hash_matches: tuple[str, ...]

    @property
    def keysets_match(self) -> bool:
        """Return whether all three inputs contain the same canonical keys."""
        expected = set(self.bibliography_keys)
        return expected == set(self.identifier_keys) == set(self.add_order_keys)

    @property
    def physical_order_matches(self) -> bool:
        """Return whether the add-order ledger equals physical bibliography order."""
        return self.bibliography_keys == self.add_order_keys


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit_legacy_workspace(
    bibliography_path: Path,
    identifiers_path: Path,
    add_order_path: Path,
) -> ConsumerAudit:
    """Audit explicitly supplied legacy inputs without modifying them."""
    library = bibtexparser.parse_file(str(bibliography_path))
    if library.failed_blocks:
        raise ValueError(f"Bibliography has {len(library.failed_blocks)} failed blocks")

    raw_identifiers = json.loads(identifiers_path.read_text(encoding="utf-8"))
    if not isinstance(raw_identifiers, dict):
        raise ValueError("identifier collection must be an object")
    identifier_data = cast(dict[str, LegacyIdentifierRecord], raw_identifiers)

    raw_add_order = json.loads(add_order_path.read_text(encoding="utf-8"))
    if not isinstance(raw_add_order, list) or any(
        not isinstance(item, str) for item in raw_add_order
    ):
        raise ValueError("add order must be an array of strings")
    add_order = cast(list[str], raw_add_order)

    matches = []
    kinds: set[str] = set()
    for key, record in identifier_data.items():
        identifiers = record["identifiers"]
        kinds.update(identifiers)
        main_value = identifiers[record["main_identifier"]]
        suffix = hashlib.sha256(main_value.encode("utf-8")).hexdigest()[:8]
        if key.endswith(f"-{suffix}"):
            matches.append(key)

    return ConsumerAudit(
        bibliography_sha256=_sha256(bibliography_path),
        identifiers_sha256=_sha256(identifiers_path),
        add_order_sha256=_sha256(add_order_path),
        bibliography_keys=tuple(entry.key for entry in library.entries),
        identifier_keys=tuple(identifier_data),
        add_order_keys=tuple(add_order),
        identifier_kinds=frozenset(kinds),
        historical_hash_matches=tuple(matches),
    )

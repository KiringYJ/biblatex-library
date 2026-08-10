"""Pure ordered bibliography and identity-index domain models."""

from collections.abc import Iterator, Sequence

from bibtexparser.library import Block
from bibtexparser.model import Entry


def _entry_aliases(entry: Entry) -> tuple[str, ...]:
    ids_fields = [field for field in entry.fields if field.key.casefold() == "ids"]
    if not ids_fields:
        return ()
    if len(ids_fields) > 1:
        raise ValueError(f"canonical key '{entry.key}' has multiple ids fields")

    raw_aliases = str(ids_fields[0].value)
    aliases = tuple(part.strip() for part in raw_aliases.split(","))
    if any(not alias for alias in aliases):
        raise ValueError(f"empty alias for canonical key '{entry.key}'")
    return aliases


class IdentityIndex:
    """Injective exact-case index over canonical keys and ``ids`` aliases."""

    def __init__(self, entries: Sequence[Entry]) -> None:
        canonical_entries: dict[str, Entry] = {}
        aliases_by_canonical: dict[str, tuple[str, ...]] = {}

        for entry in entries:
            canonical_key = entry.key
            if not canonical_key:
                raise ValueError("canonical keys must not be empty")
            if canonical_key in canonical_entries:
                raise ValueError(f"duplicate canonical key '{canonical_key}'")
            canonical_entries[canonical_key] = entry

        identities: dict[str, Entry] = dict(canonical_entries)
        alias_owners: dict[str, str] = {}
        for canonical_key, entry in canonical_entries.items():
            aliases = _entry_aliases(entry)
            seen_for_entry: set[str] = set()
            for alias in aliases:
                if alias in seen_for_entry:
                    raise ValueError(
                        f"duplicate alias '{alias}' for canonical key '{canonical_key}'"
                    )
                seen_for_entry.add(alias)

                if alias in canonical_entries:
                    raise ValueError(f"identity '{alias}' is both a canonical key and an alias")
                previous_owner = alias_owners.get(alias)
                if previous_owner is not None:
                    raise ValueError(
                        f"alias '{alias}' belongs to both '{previous_owner}' and '{canonical_key}'"
                    )
                alias_owners[alias] = canonical_key
                identities[alias] = entry
            aliases_by_canonical[canonical_key] = aliases

        self._canonical_entries = canonical_entries
        self._aliases_by_canonical = aliases_by_canonical
        self._identities = identities

    @property
    def canonical_keys(self) -> tuple[str, ...]:
        """Return canonical keys in bibliography order."""
        return tuple(self._canonical_entries)

    def resolve(self, identity: str) -> Entry:
        """Resolve a canonical key or alias using exact case-sensitive matching."""
        return self._identities[identity]

    def aliases_for(self, identity: str) -> tuple[str, ...]:
        """Return all direct aliases for the record resolved by *identity*."""
        entry = self.resolve(identity)
        return self._aliases_by_canonical[entry.key]

    def validate(self, entries: Sequence[Entry]) -> None:
        """Validate that this index was constructed for exactly *entries*."""
        if len(entries) != len(self._canonical_entries):
            raise ValueError("identity index does not match bibliography entries")
        for entry, canonical_key in zip(entries, self._canonical_entries, strict=True):
            if canonical_key != entry.key or self._canonical_entries[canonical_key] is not entry:
                raise ValueError("identity index does not match bibliography entries")
            if self._aliases_by_canonical[canonical_key] != _entry_aliases(entry):
                raise ValueError("identity index does not match bibliography entries")


class Bibliography:
    """Ordered parser blocks plus a validated canonical/alias identity index."""

    def __init__(self, blocks: Sequence[Block], identity_index: IdentityIndex) -> None:
        copied_blocks = list(blocks)
        entries = self._entries_from(copied_blocks)
        identity_index.validate(entries)
        self._blocks = copied_blocks
        self._identity_index = identity_index

    @staticmethod
    def _entries_from(blocks: Sequence[Block]) -> list[Entry]:
        return [block for block in blocks if isinstance(block, Entry)]

    @property
    def blocks(self) -> tuple[Block, ...]:
        """Return all parser blocks in their current physical order."""
        return tuple(self._blocks)

    @property
    def identity_index(self) -> IdentityIndex:
        """Return the current validated identity index."""
        return self._identity_index

    def __iter__(self) -> Iterator[Entry]:
        return iter(self._entries_from(self._blocks))

    def __len__(self) -> int:
        return len(self._identity_index.canonical_keys)

    def resolve(self, identity: str) -> Entry:
        """Resolve a canonical key or direct alias."""
        return self._identity_index.resolve(identity)

    def aliases_for(self, identity: str) -> tuple[str, ...]:
        """Return all aliases attached directly to a resolved canonical entry."""
        return self._identity_index.aliases_for(identity)

    def validate(self) -> None:
        """Validate ordered entries and the complete canonical/alias namespace."""
        entries = self._entries_from(self._blocks)
        IdentityIndex(entries)
        self._identity_index.validate(entries)

    def replace(self, identity: str, replacement: Entry) -> Entry:
        """Replace a resolved entry at its physical block position."""
        current = self.resolve(identity)
        replacement_blocks = list(self._blocks)
        position = next(index for index, block in enumerate(replacement_blocks) if block is current)
        replacement_blocks[position] = replacement
        replacement_index = IdentityIndex(self._entries_from(replacement_blocks))
        self._blocks = replacement_blocks
        self._identity_index = replacement_index
        return current

    def append(self, entry: Entry) -> Entry:
        """Append an entry after every existing parser block."""
        replacement_blocks = [*self._blocks, entry]
        replacement_index = IdentityIndex(self._entries_from(replacement_blocks))
        self._blocks = replacement_blocks
        self._identity_index = replacement_index
        return entry

    def delete(self, identity: str) -> Entry:
        """Delete a resolved entry while retaining all other block positions."""
        current = self.resolve(identity)
        replacement_blocks = [block for block in self._blocks if block is not current]
        replacement_index = IdentityIndex(self._entries_from(replacement_blocks))
        self._blocks = replacement_blocks
        self._identity_index = replacement_index
        return current

"""Pure normalization helpers for publisher/location fields."""

from dataclasses import dataclass, field

from bibtexparser.model import Entry, Field

from biblio.bibliography import Bibliography
from biblio.results import ChangeSet, FieldDelta

_PUBLISHER_LEGAL_SUFFIXES = frozenset(
    {
        "ag",
        "bv",
        "co",
        "company",
        "corp",
        "corporation",
        "gmbh",
        "inc",
        "incorporated",
        "llc",
        "llp",
        "ltd",
        "limited",
        "plc",
        "pte ltd",
        "pty ltd",
        "sa",
        "sarl",
        "sas",
        "sl",
        "spa",
    }
)


@dataclass(frozen=True, slots=True)
class PublisherLocationReport:
    """Publisher/location changes plus entries needing manual review."""

    flagged: tuple[str, ...] = ()
    fixed: tuple[str, ...] = ()
    changes: ChangeSet = field(default_factory=ChangeSet)


def normalize_publisher_location(bibliography: Bibliography) -> PublisherLocationReport:
    """Split an unambiguous ``publisher, location`` value in memory."""
    flagged: list[str] = []
    fixed: list[str] = []
    deltas: list[FieldDelta] = []

    for entry in bibliography:
        if entry.entry_type.casefold() == "article" or not _needs_location(entry):
            continue
        flagged.append(entry.key)
        split = _split_publisher(entry)
        if split is None:
            continue
        before, publisher, location = split
        fixed.append(entry.key)
        deltas.extend(
            (
                FieldDelta(entry.key, "publisher", before, publisher),
                FieldDelta(entry.key, "location", None, location),
            )
        )

    changes = ChangeSet(tuple(fixed), tuple(deltas))
    return PublisherLocationReport(tuple(flagged), tuple(fixed), changes)


def _needs_location(entry: Entry) -> bool:
    fields = entry.fields_dict
    return "publisher" in fields and "location" not in fields


def _split_publisher(entry: Entry) -> tuple[str, str, str] | None:
    publisher_field = entry.fields_dict["publisher"]
    before = str(publisher_field.value)
    if before.count(",") != 1:
        return None
    publisher, location = (part.strip() for part in before.split(",", 1))
    if not publisher or not location or _looks_like_publisher_legal_suffix(location):
        return None
    publisher_field.value = publisher
    entry.fields.append(Field("location", location))
    return before, publisher, location


def _looks_like_publisher_legal_suffix(value: str) -> bool:
    normalized = " ".join(value.replace(".", "").casefold().split())
    return normalized in _PUBLISHER_LEGAL_SUFFIXES

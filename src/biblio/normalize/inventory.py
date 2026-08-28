"""Prune redundant DOI/URL inventory values without changing citekey provenance."""

from dataclasses import dataclass, field

from biblio.bibliography import Bibliography
from biblio.identifier_collection import (
    IdentifierCollection,
    identifier_equality_token,
    identifiers_from_entry,
)
from biblio.results import ChangeSet, FieldDelta

from .doi import matches_arxiv_doi
from .url import matches_arxiv_url, matches_doi_url


@dataclass(frozen=True, slots=True)
class InventoryNormalizationReport:
    """Inventory removals and reasons to retain otherwise redundant values."""

    changes: ChangeSet = field(default_factory=ChangeSet)
    diagnostics: tuple[str, ...] = ()


def normalize_identifier_inventory(
    bibliography: Bibliography,
    records: IdentifierCollection,
    *,
    remove_urls: bool,
    remove_arxiv_dois: bool,
) -> InventoryNormalizationReport:
    """Remove proven redundancies, protecting main/history and remaining projections."""
    changed_keys: list[str] = []
    deltas: list[FieldDelta] = []
    diagnostics: list[str] = []
    for entry in bibliography:
        record = records[entry.key]
        projected = identifiers_from_entry(entry)
        arxivs = record.inventory_values("arxiv")
        dois = record.inventory_values("doi")
        protected = {
            (record.main_identifier, record.identifiers[record.main_identifier]),
            *((item.main_identifier, item.identifier) for item in record.key_history),
        }
        changed = False
        for kind, enabled in (("url", remove_urls), ("doi", remove_arxiv_dois)):
            if not enabled or kind not in record.identifiers:
                continue
            values = record.inventory_values(kind)
            removable: set[str] = set()
            for value in values:
                redundant = (
                    any(matches_arxiv_doi(value, arxiv) for arxiv in arxivs)
                    if kind == "doi"
                    else any(matches_doi_url(value, doi) for doi in dois)
                    or any(matches_arxiv_url(value, arxiv) for arxiv in arxivs)
                )
                if not redundant:
                    continue
                if (kind, value) in protected:
                    diagnostics.append(
                        f"identifier-cleanup:manual-review:{entry.key}:{kind}:key-provenance"
                    )
                    continue
                if kind in projected and identifier_equality_token(
                    kind, projected[kind]
                ) == identifier_equality_token(kind, value):
                    continue
                removable.add(value)

            primary = record.identifiers[kind]
            if primary in removable and any(value not in removable for value in values):
                removable.remove(primary)
                diagnostics.append(
                    f"identifier-cleanup:manual-review:{entry.key}:{kind}:remaining-alternates"
                )
            if not removable:
                continue
            changed = True
            if primary in removable:
                del record.identifiers[kind]
                deltas.append(FieldDelta(entry.key, f"identifiers.{kind}", primary, None))
            alternates = record.identifier_alternates.get(kind, ())
            for index, value in enumerate(alternates):
                if value in removable:
                    deltas.append(
                        FieldDelta(entry.key, f"identifier_alternates.{kind}[{index}]", value, None)
                    )
            remaining = tuple(value for value in alternates if value not in removable)
            if remaining:
                record.identifier_alternates[kind] = remaining
            else:
                record.identifier_alternates.pop(kind, None)
        if changed:
            changed_keys.append(entry.key)
    return InventoryNormalizationReport(
        ChangeSet(tuple(changed_keys), tuple(deltas)), tuple(dict.fromkeys(diagnostics))
    )

"""Pure monotonic reconciliation of BibLaTeX identifier projections."""

from copy import deepcopy
from typing import Literal

from .identifier_collection import identifier_equality_token, identifiers_from_entry
from .results import ChangeSet, IdentifierAddition, ReconcileResult
from .workspace import WorkspaceAggregate

__all__ = [
    "IdentifierAddition",
    "ReconcileResult",
    "reconcile_identifier_inventory",
]


def reconcile_identifier_inventory(aggregate: WorkspaceAggregate) -> ReconcileResult:
    """Add every missing supported BibLaTeX projection to a validated candidate.

    Equality tokens decide only whether an exact projected value is already
    represented. Existing exact values and every non-identifier artifact remain
    untouched. The input aggregate changes only after the complete candidate
    validates.
    """
    candidate = deepcopy(aggregate)
    additions: list[IdentifierAddition] = []
    changed_keys: list[str] = []
    changed_key_set: set[str] = set()

    for entry in candidate.bibliography:
        record = candidate.identifiers.get(entry.key)
        if record is None:
            continue
        for kind, exact_value in identifiers_from_entry(entry).items():
            token = identifier_equality_token(kind, exact_value)
            if any(
                identifier_equality_token(kind, current) == token
                for current in record.inventory_values(kind)
            ):
                continue

            if kind not in record.identifiers:
                record.identifiers[kind] = exact_value
                added_as: Literal["primary", "alternate"] = "primary"
            else:
                record.identifier_alternates[kind] = (
                    *record.identifier_alternates.get(kind, ()),
                    exact_value,
                )
                added_as = "alternate"
            additions.append(IdentifierAddition(entry.key, kind, exact_value, added_as))
            if entry.key not in changed_key_set:
                changed_key_set.add(entry.key)
                changed_keys.append(entry.key)

    candidate.validate()
    if not additions:
        return ReconcileResult()

    aggregate.identifiers = candidate.identifiers
    return ReconcileResult(
        additions=tuple(additions),
        changes=ChangeSet(changed_keys=tuple(changed_keys)),
    )

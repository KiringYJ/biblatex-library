"""Single in-memory dispatcher for bibliography normalization actions."""

from dataclasses import dataclass

from biblio.bibliography import Bibliography
from biblio.results import ChangeSet, NormalizeResult

from .accents import normalize_latex_accents
from .dates import rename_year_to_date_fields
from .eprint import normalize_eprint_fields
from .isbn import normalize_isbn_fields
from .journal import normalize_journal_fields
from .names import normalize_name_spacing
from .pagination import normalize_book_pagination
from .publisher import normalize_publisher_location
from .url import normalize_trivial_urls

YEAR_TO_DATE = "year-to-date"
PUBLISHER_LOCATION = "publisher-location"
EPRINT_FIELDS = "eprint-fields"
JOURNAL_FIELDS = "journal-fields"
BOOK_PAGINATION = "book-pagination"
NAME_SPACING = "name-spacing"
LATEX_ACCENTS = "latex-accents"
ISBN = "isbn"
TRIVIAL_URL = "trivial-url"
ALL = "all"

NORMALIZATION_ACTIONS = (
    YEAR_TO_DATE,
    PUBLISHER_LOCATION,
    EPRINT_FIELDS,
    JOURNAL_FIELDS,
    BOOK_PAGINATION,
    NAME_SPACING,
    LATEX_ACCENTS,
    ISBN,
    TRIVIAL_URL,
)


@dataclass(frozen=True, slots=True)
class _ActionResult:
    changes: ChangeSet
    diagnostics: tuple[str, ...] = ()


def normalize_bibliography(bibliography: Bibliography, action: str) -> NormalizeResult:
    """Run one action or all actions against one loaded bibliography.

    The aggregate is mutated only in memory. A caller owns dry-run and commit
    policy: an unchanged ``ChangeSet`` is the explicit no-op signal.
    """
    actions = NORMALIZATION_ACTIONS if action == ALL else (_validate_action(action),)
    results = tuple(_run_action(bibliography, selected) for selected in actions)
    bibliography.validate()
    return NormalizeResult(
        actions=actions,
        diagnostics=tuple(diagnostic for result in results for diagnostic in result.diagnostics),
        changes=_merge_changes([result.changes for result in results]),
    )


def _validate_action(action: str) -> str:
    if action not in NORMALIZATION_ACTIONS:
        expected = ", ".join((*NORMALIZATION_ACTIONS, ALL))
        raise ValueError(f"unknown normalization action '{action}'; expected one of: {expected}")
    return action


def _run_action(bibliography: Bibliography, action: str) -> _ActionResult:
    if action == YEAR_TO_DATE:
        return _ActionResult(rename_year_to_date_fields(bibliography))
    if action == PUBLISHER_LOCATION:
        report = normalize_publisher_location(bibliography)
        fixed = frozenset(report.fixed)
        diagnostics = tuple(
            f"{action}:manual-review:{key}" for key in report.flagged if key not in fixed
        )
        return _ActionResult(report.changes, diagnostics)
    if action == EPRINT_FIELDS:
        return _ActionResult(normalize_eprint_fields(bibliography).changes)
    if action == JOURNAL_FIELDS:
        report = normalize_journal_fields(bibliography)
        diagnostics = (
            *(
                f"{action}:manual-review:{key}:{source}->{target}:conflict"
                for key, source, target in report.conflicts
            ),
            *(
                f"{action}:manual-review:{key}:{source}->{target}:ambiguous"
                for key, source, target in report.ambiguous
            ),
        )
        return _ActionResult(report.changes, diagnostics)
    if action == BOOK_PAGINATION:
        report = normalize_book_pagination(bibliography)
        diagnostics = (
            *(f"{action}:manual-review:{key}:conflict" for key in report.conflicts),
            *(f"{action}:manual-review:{key}:ambiguous" for key in report.ambiguous),
        )
        return _ActionResult(report.changes, diagnostics)
    if action == NAME_SPACING:
        return _ActionResult(normalize_name_spacing(bibliography))
    if action == LATEX_ACCENTS:
        return _ActionResult(normalize_latex_accents(bibliography).changes)
    if action == ISBN:
        report = normalize_isbn_fields(bibliography)
        diagnostics = tuple(
            f"{action}:invalid:{key}:{value}" for key, value in report.invalid.items()
        )
        return _ActionResult(report.changes, diagnostics)
    if action == TRIVIAL_URL:
        return _ActionResult(normalize_trivial_urls(bibliography).changes)
    raise ValueError(f"unknown normalization action '{action}'")


def _merge_changes(changes: list[ChangeSet]) -> ChangeSet:
    changed_keys: list[str] = []
    seen_keys: set[str] = set()
    field_deltas = []
    alias_deltas = []
    order_delta = None

    for change in changes:
        for key in change.changed_keys:
            if key not in seen_keys:
                seen_keys.add(key)
                changed_keys.append(key)
        field_deltas.extend(change.field_deltas)
        alias_deltas.extend(change.alias_deltas)
        if change.order_delta is not None:
            if order_delta is not None:  # pragma: no cover - no action currently reorders
                raise ValueError("multiple normalization actions reported order changes")
            order_delta = change.order_delta

    return ChangeSet(
        changed_keys=tuple(changed_keys),
        field_deltas=tuple(field_deltas),
        alias_deltas=tuple(alias_deltas),
        order_delta=order_delta,
    )

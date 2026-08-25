"""Deterministic bibliography compliance checks requiring no authority lookup."""

import re
from collections.abc import Iterable

from bibtexparser.model import Entry

from .bibliography import Bibliography
from .normalize.journal import LEGACY_JOURNAL_FIELD_MAP
from .normalize.names import NAME_FIELDS, normalize_name_value
from .normalize.pagination import is_unambiguous_book_extent
from .results import AuditFinding, AuditResult

_ISSN = re.compile(r"^[0-9]{4}-[0-9]{3}[0-9Xx]$")
_YEAR_LIKE_EDITION = re.compile(r"^[12][0-9]{3}$")
_KNOWN_INVALID_FIELD_PLACEMENTS = {
    "online": ("pagetotal", "type"),
    "unpublished": ("institution", "volume"),
}


def audit_bibliography(bibliography: Bibliography) -> AuditResult:
    """Return reproducible findings based only on the parsed bibliography."""
    bibliography.validate()
    findings: list[AuditFinding] = []

    for entry in bibliography:
        fields = _field_values(entry)
        findings.extend(_journal_field_findings(entry, fields))
        findings.extend(_issn_findings(entry, fields))
        findings.extend(_book_pagination_findings(entry, fields))
        findings.extend(_edition_findings(entry, fields))
        findings.extend(_name_spacing_findings(entry, fields))
        findings.extend(_field_placement_findings(entry, fields))

    findings.extend(_journal_variant_findings(bibliography))
    findings.extend(_series_case_findings(bibliography))
    return AuditResult(clean=not findings, findings=tuple(findings))


def _field_values(entry: Entry) -> dict[str, str]:
    return {field.key.casefold(): str(field.value) for field in entry.fields}


def _journal_field_findings(entry: Entry, fields: dict[str, str]) -> tuple[AuditFinding, ...]:
    findings: list[AuditFinding] = []
    for source, target in LEGACY_JOURNAL_FIELD_MAP:
        value = fields.get(source)
        if value is None:
            continue
        target_value = fields.get(target)
        if source == "journal" and "fjournal" not in fields and "shortjournal" not in fields:
            findings.append(
                AuditFinding(
                    code="ambiguous-journal-field",
                    canonical_keys=(entry.key,),
                    fields=(source,),
                    values=(value,),
                    message="journal alone may contain a full title or an abbreviation",
                )
            )
            continue
        if target_value is not None and target_value != value:
            findings.append(
                AuditFinding(
                    code="conflicting-journal-field",
                    canonical_keys=(entry.key,),
                    fields=(source, target),
                    values=(value, target_value),
                    message=f"{source} and {target} contain different values",
                )
            )
            continue
        findings.append(
            AuditFinding(
                code="legacy-journal-field",
                canonical_keys=(entry.key,),
                fields=(source,),
                values=(value,),
                fix_action="journal-fields",
                message=f"{source} should be migrated to {target}",
            )
        )
    return tuple(findings)


def _issn_findings(entry: Entry, fields: dict[str, str]) -> tuple[AuditFinding, ...]:
    findings: list[AuditFinding] = []
    electronic = fields.get("eissn")
    if electronic is not None:
        findings.append(
            AuditFinding(
                code="nonstandard-eissn",
                canonical_keys=(entry.key,),
                fields=("eissn",),
                values=(electronic,),
                message="eissn is not a standard BibLaTeX field",
            )
        )

    value = fields.get("issn")
    if value is None:
        return tuple(findings)
    parts = tuple(part.strip() for part in value.split(","))
    if len(parts) > 1:
        findings.append(
            AuditFinding(
                code="multiple-issn",
                canonical_keys=(entry.key,),
                fields=("issn",),
                values=parts,
                message="issn contains multiple comma-separated identifiers",
            )
        )
    elif not _valid_issn(parts[0]):
        findings.append(
            AuditFinding(
                code="invalid-issn",
                canonical_keys=(entry.key,),
                fields=("issn",),
                values=parts,
                message="issn does not have valid ISSN syntax and check digit",
            )
        )
    return tuple(findings)


def _valid_issn(value: str) -> bool:
    if _ISSN.fullmatch(value) is None:
        return False
    compact = value.replace("-", "").upper()
    check = 10 if compact[-1] == "X" else int(compact[-1])
    weighted = sum(
        int(digit) * weight for digit, weight in zip(compact[:7], range(8, 1, -1), strict=True)
    )
    return (weighted + check) % 11 == 0


def _book_pagination_findings(entry: Entry, fields: dict[str, str]) -> tuple[AuditFinding, ...]:
    if entry.entry_type.casefold() != "book" or "pages" not in fields:
        return ()
    pages = fields["pages"]
    pagetotal = fields.get("pagetotal")
    if pagetotal is not None and pagetotal != pages:
        return (
            AuditFinding(
                code="book-pagination-conflict",
                canonical_keys=(entry.key,),
                fields=("pages", "pagetotal"),
                values=(pages, pagetotal),
                message="book pages and pagetotal contain different values",
            ),
        )
    if not is_unambiguous_book_extent(pages):
        return (
            AuditFinding(
                code="book-pages-review",
                canonical_keys=(entry.key,),
                fields=("pages",),
                values=(pages,),
                message="book pages is not an unambiguous total extent",
            ),
        )
    return (
        AuditFinding(
            code="book-pages-total",
            canonical_keys=(entry.key,),
            fields=("pages",),
            values=(pages,),
            fix_action="book-pagination",
            message="pages on a whole book should be stored as pagetotal",
        ),
    )


def _edition_findings(entry: Entry, fields: dict[str, str]) -> tuple[AuditFinding, ...]:
    edition = fields.get("edition")
    if edition is None or _YEAR_LIKE_EDITION.fullmatch(edition.strip()) is None:
        return ()
    return (
        AuditFinding(
            code="year-like-edition",
            canonical_keys=(entry.key,),
            fields=("edition",),
            values=(edition,),
            message="edition looks like a publication year and requires review",
        ),
    )


def _name_spacing_findings(entry: Entry, fields: dict[str, str]) -> tuple[AuditFinding, ...]:
    return tuple(
        AuditFinding(
            code="name-comma-spacing",
            canonical_keys=(entry.key,),
            fields=(field_name,),
            values=(value,),
            fix_action="name-spacing",
            message=f"{field_name} has whitespace before a name-part comma",
        )
        for field_name, value in fields.items()
        if field_name in NAME_FIELDS and normalize_name_value(value) != value
    )


def _field_placement_findings(entry: Entry, fields: dict[str, str]) -> tuple[AuditFinding, ...]:
    invalid_fields = _KNOWN_INVALID_FIELD_PLACEMENTS.get(entry.entry_type.casefold(), ())
    return tuple(
        AuditFinding(
            code="invalid-field-placement",
            canonical_keys=(entry.key,),
            fields=(field_name,),
            values=(fields[field_name],),
            message=f"{field_name} is invalid on @{entry.entry_type} in the supported datamodel",
        )
        for field_name in invalid_fields
        if field_name in fields
    )


def _journal_variant_findings(bibliography: Bibliography) -> tuple[AuditFinding, ...]:
    serial_entries: dict[str, list[tuple[str, str | None, str | None]]] = {}
    for entry in bibliography:
        fields = _field_values(entry)
        full = fields.get("journaltitle", fields.get("fjournal"))
        short = fields.get("shortjournal", fields.get("journal"))
        identifiers = _valid_serial_identifiers(fields)
        for identifier in identifiers:
            serial_entries.setdefault(identifier, []).append((entry.key, full, short))

    findings: list[AuditFinding] = []
    seen: set[tuple[str, tuple[str, ...], tuple[str, ...]]] = set()
    for identifier, records in serial_entries.items():
        for code, field_names, position, label in (
            ("journal-title-variant", ("journaltitle", "fjournal"), 1, "journal titles"),
            (
                "journal-abbreviation-variant",
                ("shortjournal", "journal"),
                2,
                "journal abbreviations",
            ),
        ):
            values = _unique_collapsed(
                value for record in records if (value := record[position]) is not None
            )
            if len(values) < 2:
                continue
            keys = tuple(record[0] for record in records if record[position] is not None)
            signature = (code, keys, values)
            if signature in seen:
                continue
            seen.add(signature)
            findings.append(
                AuditFinding(
                    code=code,
                    canonical_keys=keys,
                    fields=field_names,
                    values=values,
                    message=f"ISSN {identifier} is associated with multiple {label}",
                )
            )
    return tuple(findings)


def _valid_serial_identifiers(fields: dict[str, str]) -> tuple[str, ...]:
    values = tuple(value for name in ("issn", "eissn") if (value := fields.get(name)))
    identifiers: list[str] = []
    for value in values:
        for part in value.split(","):
            candidate = part.strip().upper()
            if _valid_issn(candidate) and candidate not in identifiers:
                identifiers.append(candidate)
    return tuple(identifiers)


def _series_case_findings(bibliography: Bibliography) -> tuple[AuditFinding, ...]:
    groups: dict[str, list[tuple[str, str]]] = {}
    for entry in bibliography:
        value = _field_values(entry).get("series")
        if value is None:
            continue
        collapsed = " ".join(value.split())
        groups.setdefault(collapsed.casefold(), []).append((entry.key, collapsed))

    findings: list[AuditFinding] = []
    for records in groups.values():
        values = _unique_collapsed(value for _key, value in records)
        if len(values) < 2:
            continue
        findings.append(
            AuditFinding(
                code="series-case-variant",
                canonical_keys=tuple(key for key, _value in records),
                fields=("series",),
                values=values,
                message="series values differ only by letter case",
            )
        )
    return tuple(findings)


def _unique_collapsed(values: Iterable[str]) -> tuple[str, ...]:
    unique: list[str] = []
    for raw in values:
        value = " ".join(raw.split())
        if value not in unique:
            unique.append(value)
    return tuple(unique)

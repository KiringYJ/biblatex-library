"""Pure validation of the canonical BibLaTeX bibliography model."""

import re

from .bibliography import Bibliography
from .identifiers import hexagon_comparison_token
from .results import ValidateResult

_GENERATED_CITEKEY = re.compile(r"^[a-z]+-(?:[0-9]{4}|unknown)-[0-9a-f]{8}$")


def validate_bibliography(bibliography: Bibliography) -> ValidateResult:
    """Check parse/model, identity, citekey, and core BibLaTeX semantics."""
    issues: list[str] = []
    try:
        bibliography.validate()
    except ValueError as error:
        return ValidateResult(valid=False, issues=(str(error),))

    for entry in bibliography:
        fields: dict[str, str] = {}
        for field in entry.fields:
            name = field.key.casefold()
            if name in fields:
                issues.append(f"entry '{entry.key}' has duplicate '{name}' fields")
            else:
                fields[name] = str(field.value)

        if not _GENERATED_CITEKEY.fullmatch(entry.key):
            issues.append(f"entry '{entry.key}' does not have a generated citekey shape")
        if not entry.entry_type.strip():
            issues.append(f"entry '{entry.key}' has an empty entry type")
        if not any(name in fields for name in ("title", "journaltitle", "booktitle")):
            issues.append(f"entry '{entry.key}' has no title-bearing field")

        eprinttype = fields.get("eprinttype", fields.get("archiveprefix", ""))
        if eprinttype.strip().casefold() == "arxiv" and not fields.get("eprint", "").strip():
            issues.append(f"entry '{entry.key}' declares arXiv without a nonempty eprint")
        if "eprintclass" in fields and eprinttype.strip().casefold() not in {"arxiv", "hexagon"}:
            issues.append(
                f"entry '{entry.key}' has eprintclass without eprinttype=arxiv or hexagon"
            )
        types = [
            fields[name].strip().casefold()
            for name in ("eprinttype", "archiveprefix")
            if name in fields
        ]
        if "hexagon" in types:
            if any(value != "hexagon" for value in types):
                issues.append(f"entry '{entry.key}' has conflicting Hexagon eprint aliases")
            if (
                "primaryclass" in fields
                and "eprintclass" in fields
                and fields["primaryclass"] != fields["eprintclass"]
            ):
                issues.append(f"entry '{entry.key}' has conflicting Hexagon class aliases")
            eprint = fields.get("eprint", "")
            if not eprint.strip():
                issues.append(f"entry '{entry.key}' declares Hexagon without a nonempty eprint")
            else:
                try:
                    hexagon_comparison_token(eprint)
                except ValueError as error:
                    issues.append(f"entry '{entry.key}' has an invalid Hexagon eprint: {error}")

    return ValidateResult(valid=not issues, issues=tuple(issues))
